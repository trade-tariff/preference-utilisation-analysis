import os
import sys
import time
from pathlib2 import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
import xlsxwriter
import ssl

from classes.database import Database
from classes.functions import functions as f
from classes.quota_definition import QuotaDefinition, QuotaExclusion, QuotaCommodity
from classes.quota_balance import QuotaBalance
from classes.measure_type import MeasureType
from classes.geographical_area import GeographicalArea
from classes.commodity import Commodity
from classes.footnote import Footnote
from classes.measure import Measure
from classes.measure_component import MeasureComponent
from classes.measure_condition import MeasureCondition
from classes.measure_excluded_geographical_area import MeasureExcludedGeographicalArea
from classes.geographical_area_member import GeographicalAreaMember
from classes.aws_bucket import AwsBucket
from classes.sendgrid_mailer import SendgridMailer


class Application(object):
    def __init__(self):
        self.message_string = ""
        load_dotenv('.env')

        self.DATABASE = os.getenv('DATABASE_UK')
        self.MEASURES_FILENAME = os.getenv('MEASURES_FILENAME')
        self.GEO_FILENAME = os.getenv('GEO_FILENAME')

        self.PLACEHOLDER_FOR_EMPTY_DESCRIPTIONS = os.getenv('PLACEHOLDER_FOR_EMPTY_DESCRIPTIONS')
        self.write_to_aws = int(os.getenv('WRITE_TO_AWS'))

        if "testmail" not in sys.argv[0]:
            # Check whether UK or XI
            if ("dest" not in sys.argv[0]):
                self.get_scope()
            else:
                self.scope = "uk"

            # Date of the report
            self.get_date()
            self.get_folders()
            self.get_process_scope()
            self.get_filename()
        self.create_ssl_unverified_context()

    def create_ssl_unverified_context(self):
        ssl._create_default_https_context = ssl._create_unverified_context

    def get_filename(self):
        self.file_only = self.MEASURES_FILENAME + "_{dt}.xlsx".format(dt=self.SNAPSHOT_DATE)
        self.filename = os.path.join(self.dated_folder, self.file_only)

        self.geo_file_only = "trade_groups_{dt}.xlsx".format(dt=self.SNAPSHOT_DATE)
        self.geo_filename = os.path.join(self.dated_folder, self.geo_file_only)

    def create_preference_utilisation_analysis(self):
        self.get_reference_data()
        self.write_geographical_area_members()
        self.get_quota_balances()
        self.get_quotas()
        self.assign_quota_balances()
        self.get_commodities()

    def get_commodities(self):
        # Create the Excel document right at the start
        # Also write the table headers
        self.workbook = xlsxwriter.Workbook(
            self.filename, {'strings_to_urls': False})
        self.bold = self.workbook.add_format({'bold': True})
        self.worksheet = self.workbook.add_worksheet(self.SNAPSHOT_DATE)
        fields = [
            ["trackedmodel_ptr_id", 20],
            ["commodity__sid", 20],
            ["commodity__code", 20],
            ["commodity__indent", 20],
            ["commodity__description", 50],
            ["measure__sid", 20],
            ["measure__type__id", 20],
            ["measure__type__description", 20],
            ["measure__additional_code__code", 20],
            ["measure__additional_code__description", 20],
            ["measure__duty_expression", 20],
            ["measure__effective_start_date", 20],
            ["measure__effective_end_date", 20],
            ["measure_reduction_indicator", 20],
            ["measure__footnotes", 20],
            ["measure__conditions", 20],
            ["measure__geographical_area__sid", 20],
            ["measure__geographical_area__id", 20],
            ["measure__geographical_area__description", 20],
            ["measure__excluded_geographical_areas__ids", 20],
            ["measure__excluded_geographical_areas__descriptions", 20],
            ["measure__quota__order_number", 20],
            ["measure__quota__available", 20],
            ["measure__regulation__id", 20],
            ["measure__regulation__url", 20]
        ]

        col = 0
        for field, column_width in (fields):
            column_string = chr(col + 65) + ":" + chr(col + 65)
            self.worksheet.set_column(column_string, column_width)
            self.worksheet.write(0, col, field, self.bold)
            col += 1

        self.row_count = 1
        for i in range(self.start, self.end):
            self.start_loop_timer(
                "Creating data for commodity codes starting with " + str(i))
            self.commodities = []
            self.get_measure_components(i)
            self.get_measure_conditions(i)
            self.get_measure_excluded_geographical_areas(i)
            self.get_measures(i)
            # self.get_footnotes(i)
            self.assign_measure_components_to_measures()
            self.assign_measure_conditions_to_measures()
            # self.assign_footnotes_to_measures()
            self.get_condition_strings()
            self.assign_measure_excluded_geographical_areas()
            self.get_quota_statuses()
            self.sort_measures()
            self.create_measure_duties()

            iteration = str(i) + "%"

            sql = """select goods_nomenclature_sid, goods_nomenclature_item_id, producline_suffix,
            validity_start_date, validity_end_date, description, number_indents, chapter, node,
            leaf, significant_digits
            from utils.goods_nomenclature_export_new(%s, %s) order by 2, 3"""

            d = Database()
            params = [
                iteration,
                self.SNAPSHOT_DATE
            ]
            rows = d.run_query(sql, params)
            for row in rows:
                commodity = Commodity()
                commodity.goods_nomenclature_item_id = row[1]
                commodity.goods_nomenclature_sid = row[0]
                commodity.productline_suffix = row[2]
                commodity.validity_start_date = self.YYYYMMDD(row[3])
                commodity.validity_end_date = self.YYYYMMDD(row[4])
                commodity.description = row[5]
                commodity.number_indents = int(row[6])
                commodity.leaf = int(str(row[9]))
                commodity.significant_digits = int(row[10])
                commodity.cleanse_description()
                self.commodities.append(commodity)

            self.assign_measures_to_commodities()
            self.build_commodity_hierarchy()
            self.apply_commodity_inheritance()
            self.extract_data()

        # Actions to be completed after the end of the last iteration
        self.start_timer("Saving file")
        self.worksheet.freeze_panes(1, 0)
        self.worksheet.autofilter('A1:Y' + str(self.row_count))
        self.workbook.close()
        self.end_timer("Saving file")
        self.load_and_mail()

    def load_and_mail(self):
        # Load to AWS (main measures file)
        my_file = os.path.join(os.getcwd(), "_export", self.SNAPSHOT_DATE, self.file_only)
        aws_path = self.MEASURES_FILENAME + "/" + self.file_only
        url = self.load_to_aws("Loading preference utilisation analysis file " + self.SNAPSHOT_DATE, my_file, aws_path)

        # Load to AWS (members file)
        my_file = os.path.join(os.getcwd(), "_export", self.SNAPSHOT_DATE, self.geo_file_only)
        aws_path = self.GEO_FILENAME + "/" + self.geo_file_only
        url2 = self.load_to_aws("Loading trade groups file " + self.SNAPSHOT_DATE, my_file, aws_path)

        # Send the email
        if url is not None:
            subject = "Preference utilisation analysis file for " + self.SNAPSHOT_DATE
            content = "<p>Hello,</p>"
            content += "<p><b>Preference utilisation analysis file</b><br>"
            content += "The preference utilisation analysis file for " + self.SNAPSHOT_DATE + " has been uploaded to this location:</p><p>" + url + "</p>"

            content += "<p><b>Trade groups file</b><br>"
            content += "The trade groups file for " + self.SNAPSHOT_DATE + " has been uploaded to this location:</p><p>" + url2 + "</p>"
            content += "<p>Thank you.</p>"
            attachment_list = []
            self.send_email_message(subject, content, attachment_list)

    def get_quota_statuses(self):
        for m in self.measures:
            m.get_quota_status()
            m.check_exhausted()

    def apply_commodity_inheritance(self):
        self.start_timer("Applying inheritance")
        for commodity in self.commodities:
            commodity.apply_commodity_inheritance()
            commodity.sort_measures()
        self.end_timer("Applying inheritance")

    def get_footnotes(self, i):
        self.start_timer("Getting footnotes")
        self.footnotes = []
        sql = """select m.measure_sid, f.footnote_type_id || f.footnote_id  as footnote
        from footnotes f, footnote_association_measures fam, measures m
        where fam.footnote_type_id = f.footnote_type_id
        and fam.footnote_id = f.footnote_id
        and fam.measure_sid = m.measure_sid
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date >= '""" + self.SNAPSHOT_DATE + """')
        and left(m.goods_nomenclature_item_id, 1) = '""" + str(i) + """'
        """
        d = Database()
        rows = d.run_query(sql.replace("\n", ""))
        for row in rows:
            footnote = Footnote()
            footnote.measure_sid = row[0]
            footnote.footnote = row[1]
            self.footnotes.append(footnote)

        self.footnotes.sort(key=lambda x: x.measure_sid, reverse=False)
        self.end_timer("Getting footnotes")

    def get_condition_strings(self):
        for m in self.measures:
            m.get_condition_string()

    def extract_data(self):
        for commodity in self.commodities:
            if commodity.leaf == 1:
                for measure in commodity.measures:
                    # Index
                    self.worksheet.write(self.row_count, 1, str(self.row_count))

                    # Comm code-related fields
                    self.worksheet.write(self.row_count, 1, str(commodity.goods_nomenclature_sid))
                    self.worksheet.write(self.row_count, 2, commodity.goods_nomenclature_item_id)
                    self.worksheet.write(self.row_count, 3, str(commodity.number_indents))
                    self.worksheet.write(self.row_count, 4, commodity.description)

                    # Measure-related fields
                    self.worksheet.write(self.row_count, 5, str(measure.measure_sid))
                    self.worksheet.write(self.row_count, 6, measure.measure_type_id)
                    self.worksheet.write(self.row_count, 7, measure.measure_type_description)
                    self.worksheet.write(self.row_count, 8, measure.additional_code)
                    self.worksheet.write(self.row_count, 9, measure.additional_code_description)
                    self.worksheet.write(self.row_count, 10, measure.english_duty_string)
                    self.worksheet.write(self.row_count, 11, measure.validity_start_date)
                    self.worksheet.write(self.row_count, 12, measure.validity_end_date)
                    self.worksheet.write(self.row_count, 13, f.process_null(measure.reduction_indicator))
                    self.worksheet.write(self.row_count, 14, measure.footnotes_string)
                    self.worksheet.write(self.row_count, 15, measure.condition_string)
                    self.worksheet.write(self.row_count, 16, str(measure.geographical_area_sid))
                    self.worksheet.write(self.row_count, 17, measure.geographical_area_id)
                    self.worksheet.write(self.row_count, 18, measure.geographical_area_description)
                    self.worksheet.write(self.row_count, 19, measure.measure_excluded_geographical_areas_string)
                    self.worksheet.write(self.row_count, 20, measure.measure_excluded_geographical_area_descriptions_string)
                    self.worksheet.write(self.row_count, 21, measure.ordernumber)
                    self.worksheet.write(self.row_count, 22, measure.quota_status)
                    self.worksheet.write(self.row_count, 23, measure.measure_generating_regulation_id)
                    self.worksheet.write(self.row_count, 24, measure.regulation_url)

                    self.row_count += 1

    def assign_measures_to_commodities(self):
        self.start_timer("Assigning measures to commodities")
        start_point = 0
        for measure in self.measures:
            for i in range(start_point, len(self.commodities)):
                commodity = self.commodities[i]
                if commodity.productline_suffix == "80":
                    if measure.goods_nomenclature_item_id == commodity.goods_nomenclature_item_id:
                        start_point = i
                        commodity.measures.append(measure)
                        break

        self.end_timer("Assigning measures to commodities")

    def create_measure_duties(self):
        self.start_timer("Creating measure duties")
        for measure in self.measures:
            measure.create_measure_duties()

        self.end_timer("Creating measure duties")

    def sort_measures(self):
        self.start_timer("Sorting measures")
        self.measures.sort(key=lambda x: (
            x.additional_code_id is None, x.additional_code_id), reverse=False)
        self.measures.sort(key=lambda x: (
            x.additional_code_type_id is None, x.additional_code_type_id), reverse=False)
        self.measures.sort(key=lambda x: (
            x.ordernumber is None, x.ordernumber), reverse=False)
        self.measures.sort(key=lambda x: x.geographical_area_id, reverse=False)
        self.measures.sort(key=lambda x: x.measure_type_id, reverse=False)
        self.measures.sort(
            key=lambda x: x.goods_nomenclature_item_id, reverse=False)
        self.end_timer("Sorting measures")

    def get_measures(self, iteration):
        # Get measures
        self.start_timer("Getting measures")
        self.measures = []

        # Sort by measure SID to speed up processing in the assignment functions later
        sql = """select m.*, mt.measure_type_series_id,
        mt.measure_component_applicable_code, mt.trade_movement_code, mtd.description as measure_type_description
        from utils.materialized_measures_real_end_dates m, measure_types mt, measure_type_descriptions mtd
        where m.measure_type_id = mt.measure_type_id
        and m.measure_type_id = mtd.measure_type_id
        and left(goods_nomenclature_item_id, """ + str(len(str(iteration))) + """) = '""" + str(iteration) + """'
        and (m.validity_end_date is null or m.validity_end_date >= '""" + self.SNAPSHOT_DATE + """')
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and m.measure_type_id not in ('109', '110', '111')
        order by measure_sid;"""

        d = Database()
        rows = d.run_query(sql.replace("\n", ""))
        for row in rows:
            measure = Measure()
            measure.measure_sid = row[0]
            measure.goods_nomenclature_item_id = row[1]
            measure.geographical_area_id = row[2]
            measure.measure_type_id = row[3]
            measure.measure_generating_regulation_id = row[4]
            measure.ordernumber = row[5]
            measure.reduction_indicator = row[6]
            measure.additional_code_type_id = row[7]
            measure.additional_code_id = row[8]
            measure.additional_code = f.null_to_string(row[9])
            measure.measure_generating_regulation_role = row[10]
            measure.justification_regulation_role = row[11]
            measure.justification_regulation_id = row[12]
            measure.stopped_flag = row[13]
            measure.geographical_area_sid = row[14]
            measure.goods_nomenclature_sid = row[15]
            measure.additional_code_sid = row[16]
            measure.validity_start_date = row[18]
            measure.validity_end_date = row[19]
            measure.operation_date = row[20]
            measure.measure_type_series_id = row[21]
            measure.measure_component_applicable_code = int(row[22])
            measure.trade_movement_code = row[23]
            measure.measure_type_description = row[24]
            measure.get_import_export()
            measure.get_additional_code_description()
            measure.get_geographical_area_description()
            measure.get_regulation_url()
            measure.get_footnote_string()

            self.measures.append(measure)

        self.end_timer("Getting measures")

    def assign_measure_components_to_measures(self):
        # Assign the measure components to the measures
        self.start_timer("Assigning measure components to measures")
        start_point = 0
        for measure_component in self.measure_components:
            for i in range(start_point, len(self.measures)):
                measure = self.measures[i]
                if measure.measure_sid == measure_component.measure_sid:
                    start_point = i
                    measure.measure_components.append(measure_component)
                    break

        self.end_timer("Assigning measure components to measures")

    def assign_measure_excluded_geographical_areas(self):
        # Assign measure exclusions to measures
        self.start_timer(
            "Assigning measure excluded geographical areas to measures")
        start_point = 0
        for measure_excluded_geographical_area in self.measure_excluded_geographical_areas:
            for i in range(start_point, len(self.measures)):
                measure = self.measures[i]
                if measure.measure_sid == measure_excluded_geographical_area.measure_sid:
                    start_point = i
                    measure.measure_excluded_geographical_areas.append(
                        measure_excluded_geographical_area)
                    break

        for measure in self.measures:
            measure.get_geographical_area_exclusions()

        self.end_timer(
            "Assigning measure excluded geographical areas to measures")

    def assign_measure_conditions_to_measures(self):
        # This is used for working out if there is a chance that the heading is ex head
        # If there is a 'Y' condition, then this typically means that there are exclusions
        self.start_timer("Assigning measure conditions to measures")

        start_point = 0
        for measure_condition in self.measure_conditions:
            for i in range(start_point, len(self.measures)):
                measure = self.measures[i]
                if measure.measure_sid == measure_condition.measure_sid:
                    start_point = i
                    measure.measure_conditions.append(measure_condition)
                    break

        self.end_timer("Assigning measure conditions to measures")

    def assign_footnotes_to_measures(self):
        return
        self.start_timer("Assigning footnotes to measures")
        start_point = 0
        for footnote in self.footnotes:
            for i in range(start_point, len(self.measures)):
                measure = self.measures[i]
                if measure.measure_sid == footnote.measure_sid:
                    start_point = i
                    measure.footnotes.append(footnote)
                    break

        self.end_timer("Assigning footnotes to measures")

    def get_measure_components(self, iteration):
        # Get measure components
        self.start_timer("Getting measure components")
        self.measure_components = []
        sql = """select mc.measure_sid, mc.duty_expression_id, mc.duty_amount, mc.monetary_unit_code,
        mc.measurement_unit_code, mc.measurement_unit_qualifier_code, m.goods_nomenclature_item_id
        from measure_components mc, utils.materialized_measures_real_end_dates m
        where m.measure_sid = mc.measure_sid
        and left(m.goods_nomenclature_item_id, """ + str(len(str(iteration))) + """) = '""" + str(iteration) + """'
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        order by m.measure_sid, mc.duty_expression_id;"""
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            measure_component = MeasureComponent()
            measure_component.measure_sid = row[0]
            measure_component.duty_expression_id = row[1]
            measure_component.duty_amount = row[2]
            measure_component.monetary_unit_code = row[3]
            measure_component.measurement_unit_code = row[4]
            measure_component.measurement_unit_qualifier_code = row[5]
            measure_component.goods_nomenclature_item_id = row[6]
            measure_component.get_english_component_definition()
            self.measure_components.append(measure_component)

        self.end_timer("Getting measure components")

    def get_measure_conditions(self, iteration):
        self.start_timer("Getting measure conditions")
        self.measure_conditions = []
        self.measure_conditions_exemption = []
        self.measure_conditions_licence = []

        # First, get all measure conditions - these are needed to add to the CSV version of the file
        sql = """
        select mc.measure_condition_sid, mc.measure_sid, mc.condition_code, mc.component_sequence_number,
        mc.condition_duty_amount, mc.condition_monetary_unit_code, mc.condition_measurement_unit_code,
        mc.condition_measurement_unit_qualifier_code, mc.action_code, mc.certificate_type_code, mc.certificate_code
        from measure_conditions mc, utils.materialized_measures_real_end_dates m
        where m.measure_sid = mc.measure_sid
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and left(m.goods_nomenclature_item_id, """ + str(len(str(iteration))) + """) = '""" + str(iteration) + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        order by mc.measure_sid, mc.condition_code, mc.component_sequence_number
        """
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            mc = MeasureCondition()
            mc.measure_condition_sid = row[0]
            mc.measure_sid = row[1]
            mc.condition_code = row[2]
            mc.component_sequence_number = row[3]
            mc.condition_duty_amount = row[4]
            mc.condition_monetary_unit_code = row[5]
            mc.condition_measurement_unit_code = row[6]
            mc.condition_measurement_unit_qualifier_code = row[7]
            mc.action_code = row[8]
            mc.certificate_type_code = f.process_null(row[9])
            mc.certificate_code = f.process_null(row[10])
            mc.get_condition_string()
            self.measure_conditions.append(mc)

        self.end_timer("Getting measure conditions")

    def get_measure_excluded_geographical_areas(self, iteration):
        # Get measure geo exclusions
        self.start_timer("Getting measure excluded geographical areas")
        self.measure_excluded_geographical_areas = []
        sql = """select mega.measure_sid, mega.excluded_geographical_area, mega.geographical_area_sid
        from measure_excluded_geographical_areas mega, utils.materialized_measures_real_end_dates m
        where m.measure_sid = mega.measure_sid
        and left(m.goods_nomenclature_item_id, """ + str(len(str(iteration))) + """) = '""" + str(iteration) + """'
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        and mega.excluded_geographical_area != 'EU'
        order by mega.measure_sid, mega.excluded_geographical_area;"""
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            measure_excluded_geographical_area = MeasureExcludedGeographicalArea()
            measure_excluded_geographical_area.measure_sid = row[0]
            measure_excluded_geographical_area.excluded_geographical_area = row[1]
            measure_excluded_geographical_area.geographical_area_sid = row[2]
            measure_excluded_geographical_area.get_description()

            self.measure_excluded_geographical_areas.append(
                measure_excluded_geographical_area)
        self.end_timer("Getting measure excluded geographical areas")

    def build_commodity_hierarchy(self):
        # Builds the commodity hierarchy
        self.rebase_chapters()
        self.start_timer("Building commodity hierarchy")
        commodity_count = len(self.commodities)
        for loop in range(0, commodity_count):
            commodity = self.commodities[loop]
            current_indent = commodity.number_indents
            for loop2 in range(loop - 1, -1, -1):
                commodity2 = self.commodities[loop2]
                if commodity2.number_indents < current_indent:
                    commodity.hierarchy.append(commodity2)
                    commodity.hierarchy_sids.append(
                        commodity2.goods_nomenclature_sid)
                    current_indent = commodity2.number_indents
                if commodity2.number_indents == -1:
                    break
            commodity.hierarchy.reverse()

        self.end_timer("Building commodity hierarchy")

        self.end_timer("Building commodity hierarchy")

    def get_folders(self):
        self.current_folder = os.getcwd()
        self.data_folder = os.path.join(self.current_folder, "data")
        self.reference_folder = os.path.join(self.data_folder, "reference")
        self.data_in_folder = os.path.join(self.data_folder, "in")
        self.data_out_folder = os.path.join(self.data_folder, "out")
        self.export_folder = os.path.join(self.current_folder, "_export")

        # Make the date-specific folder
        date_time_obj = datetime.strptime(self.SNAPSHOT_DATE, '%Y-%m-%d')
        self.year = date_time_obj.strftime("%Y")
        self.month = date_time_obj.strftime("%b").lower()
        self.month2 = date_time_obj.strftime("%m").lower()
        self.day = date_time_obj.strftime("%d")

        self.date_string = self.year + "-" + self.month2 + "-" + self.day
        self.dated_folder = os.path.join(self.export_folder, self.date_string)
        os.makedirs(self.dated_folder, exist_ok=True)

        # Under the date-specific folder, also make a scope (UK/XI) folder
        # self.scope_folder = os.path.join(self.dated_folder, self.scope)
        # os.makedirs(self.scope_folder, exist_ok=True)

        # Finally, make the destination folders
        # self.csv_folder = os.path.join(self.scope_folder, "csv")
        # self.excel_folder = os.path.join(self.scope_folder, "csv")
        # self.log_folder = os.path.join(self.scope_folder, "logs")
        # self.log_filename = os.path.join(self.log_folder, "etf_creation_log.txt")

        # os.makedirs(self.csv_folder, exist_ok=True)
        # os.makedirs(self.excel_folder, exist_ok=True)
        # os.makedirs(self.log_folder, exist_ok=True)

    def get_date(self):
        if len(sys.argv) > 4:
            d = sys.argv[4].lower()
            date_format = "%Y-%m-%d"
            try:
                datetime.strptime(d, date_format)
                self.SNAPSHOT_DATE = d
                self.COMPARISON_DATE = datetime.strptime(
                    d, '%Y-%m-%d') - timedelta(days=7)
            except ValueError:
                print(
                    "This is the incorrect date string format. It should be YYYY-MM-DD")
                sys.exit()
        else:
            d = datetime.now()
            self.SNAPSHOT_DATE = d.strftime('%Y-%m-%d')
            self.COMPARISON_DATE = d - timedelta(days=7)

    def get_scope(self):
        # Takes arguments from the command line to identify
        # whether to process UK or EU data
        if len(sys.argv) > 1:
            self.scope = sys.argv[1].lower()
        else:
            print("Please specify the country scope (uk or xi)")
            sys.exit()

        if self.scope not in ("uk", "xi"):
            print("Please specify the country scope (uk or xi)")
            sys.exit()

        load_dotenv('.env')
        if self.scope == "uk":
            self.DATABASE = os.getenv('DATABASE_UK')
        else:
            self.DATABASE = os.getenv('DATABASE_EU')

    def get_process_scope(self):
        # Takes arguments from the command line to identify
        # which commodities to process
        if len(sys.argv) > 2:
            self.start = int(sys.argv[2])
            if len(sys.argv) > 3:
                self.end = int(sys.argv[3])
            else:
                self.end = 10
        else:
            self.start = 0
            self.end = 10

    def get_reference_data(self):
        self.get_measure_types_friendly()
        self.get_geographical_areas_friendly()
        self.get_geographical_area_members()
        self.get_additional_codes_friendly()
        self.get_base_regulations()

    def get_measure_types_friendly(self):
        sql = """select mt.measure_type_id, mtd.description
        from measure_types mt, measure_type_descriptions mtd
        where mt.measure_type_id = mtd.measure_type_id
        and mt.validity_end_date is null
        order by 1
        """
        self.measure_types_friendly = {}
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            self.measure_types_friendly[row[0]] = row[1]

    def get_additional_codes_friendly(self):
        sql = """
        select distinct on (ac.additional_code_sid)
        ac.additional_code_sid, acd.description
        from additional_codes ac, additional_code_description_periods acdp, additional_code_descriptions acd
        where ac.additional_code_sid = acdp.additional_code_sid
        and ac.additional_code_sid = acd.additional_code_sid
        order by ac.additional_code_sid, acdp.validity_end_date desc;
        """
        self.additional_codes_friendly = {}
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            self.additional_codes_friendly[row[0]] = row[1].replace('"', '')

    def get_base_regulations(self):
        sql = """
        select base_regulation_id, information_text n
        from base_regulations br where information_text ilike '%http%'
        order by 2;
        """
        self.base_regulations = {}
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            base_regulation_id = row[0]
            information_text = f.null_to_string(row[1])
            information_text = f.process_url(information_text)
            self.base_regulations[base_regulation_id] = information_text

    def get_geographical_areas_friendly(self):
        sql = """SELECT g.geographical_area_sid,
        geo1.geographical_area_id,
        geo1.description
        FROM geographical_area_descriptions geo1,
        geographical_areas g
        WHERE g.geographical_area_id::text = geo1.geographical_area_id::text
        AND (geo1.geographical_area_description_period_sid IN ( SELECT max(geo2.geographical_area_description_period_sid) AS max
        FROM geographical_area_descriptions geo2
        WHERE geo1.geographical_area_id::text = geo2.geographical_area_id::text))
        and g.validity_end_date is null
        ORDER BY geo1.geographical_area_id;"""
        self.geographical_areas_friendly = {}
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            description = f.null_to_string(row[2]).replace(",", "")
            self.geographical_areas_friendly[row[0]] = description

    def get_geographical_area_members(self):
        self.start_timer("Getting geographical area members")
        sql = """
        with cta_ga as (
            select distinct on (ga.geographical_area_sid)
            ga.geographical_area_sid, ga.geographical_area_id, description
            from geographical_area_descriptions gad, geographical_area_description_periods gadp, geographical_areas ga
            where ga.geographical_area_sid = gad.geographical_area_sid
            and gad.geographical_area_description_period_sid = gadp.geographical_area_description_period_sid
            and gad.description is not null
            and gadp.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
            and (gadp.validity_end_date >= '""" + self.SNAPSHOT_DATE + """' or gadp.validity_end_date is null)
            and ga.validity_start_date  <= '""" + self.SNAPSHOT_DATE + """'
            and (ga.validity_end_date >= '""" + self.SNAPSHOT_DATE + """' or ga.validity_end_date is null)
            order by ga.geographical_area_sid, ga.geographical_area_id, gad.description, gadp.validity_start_date desc
        )
        select parent.geographical_area_id, parent.description,
        child.geographical_area_id, child.description
        from geographical_area_memberships gam, cta_ga as parent, cta_ga as child
        where gam.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and gam.geographical_area_group_sid = parent.geographical_area_sid
        and gam.geographical_area_sid = child.geographical_area_sid
        and (gam.validity_end_date is null or gam.validity_end_date >= '""" + self.SNAPSHOT_DATE + """')
        order by 1, 3;
        """
        self.geographical_area_members = []
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            gam = GeographicalAreaMember(row[0], row[1], row[2], row[3])
            self.geographical_area_members.append(gam)

        self.end_timer("Getting geographical area members")

    def write_geographical_area_members(self):
        self.workbook = xlsxwriter.Workbook(self.geo_filename, {'strings_to_urls': False})
        self.bold = self.workbook.add_format({'bold': True})
        self.worksheet = self.workbook.add_worksheet(self.SNAPSHOT_DATE)

        fields = [
            ["parent_id", 20],
            ["parent_description", 75],
            ["child_id", 20],
            ["child_description", 75]
        ]
        col = 0
        for field, column_width in (fields):
            column_string = chr(col + 65) + ":" + chr(col + 65)
            self.worksheet.set_column(column_string, column_width)
            self.worksheet.write(0, col, field, self.bold)
            col += 1

        self.row_count = 1
        for ga in self.geographical_area_members:
            self.worksheet.write(self.row_count, 0, ga.parent_id)
            self.worksheet.write(self.row_count, 1, ga.parent_description)
            self.worksheet.write(self.row_count, 2, ga.child_id)
            self.worksheet.write(self.row_count, 3, ga.child_description)
            self.row_count += 1

        self.worksheet.freeze_panes(1, 0)
        self.worksheet.autofilter('A1:D' + str(self.row_count))
        self.workbook.close()

    def get_quota_balances(self):
        self.quota_balances = []
        self.start_timer("Getting quota balances")
        sql = """with cte as (
            select distinct on (qbe.quota_definition_sid)
            qd.quota_order_number_id, qbe.quota_definition_sid, qbe.occurrence_timestamp,
            qbe.new_balance, qd.quota_order_number_sid, qd.validity_start_date, qd.validity_end_date
            from quota_balance_events qbe, quota_definitions qd
            where qd.quota_definition_sid = qbe.quota_definition_sid
            and qd.quota_order_number_id like '05%'
            and qd.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
            and qbe.occurrence_timestamp <= '""" + self.SNAPSHOT_DATE + """'
            order by qbe.quota_definition_sid, qd.quota_order_number_id, qbe.occurrence_timestamp desc
        )
        select * from cte order by quota_order_number_id;
        """
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            qb = QuotaBalance(row[0], row[1], row[2], row[3], row[4], row[5], row[6])
            self.quota_balances.append(qb)
        self.end_timer("Getting quota balances")

    def assign_quota_balances(self):
        self.start_timer("Assigning quota balances")
        for qd in self.quota_definitions:
            for qb in self.quota_balances:
                if qb.quota_definition_sid == qd.quota_definition_sid:
                    qd.quota_balances.append(qb)
                    qd.quota_balance = qb.new_balance
        self.end_timer("Assigning quota balances")

        # Firstly, get the volumes from the initial volume in the definitions table
        self.quota_order_numbers = {}
        for qd in self.quota_definitions:
            if qd.quota_order_number_id == "050076":
                a = 1
            if qd.quota_order_number_id not in self.quota_order_numbers:
                self.quota_order_numbers[qd.quota_order_number_id] = qd.initial_volume

        # Secondly, overlay the quota balances
        for qd in self.quota_definitions:
            if qd.quota_balance != 999999999999:
                self.quota_order_numbers[qd.quota_order_number_id] = qd.quota_balance

    def get_quotas(self):
        # Get the quotas that are referenced in measures for the given period
        self.start_timer("Getting and writing all quota definitions for CSV export")
        self.quota_commodities = []
        sql = """
        select ordernumber, string_agg(distinct goods_nomenclature_item_id, '|' order by m.goods_nomenclature_item_id)
        from utils.materialized_measures_real_end_dates m
        where ordernumber like '05%'
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        group by ordernumber
        order by ordernumber
        """
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            quota_commodity = QuotaCommodity()
            quota_commodity.quota_order_number_id = row[0]
            quota_commodity.commodities = row[1]

            self.quota_commodities.append(quota_commodity)

        # Get quota exclusions for all quotas
        self.quota_exclusions = []
        sql = """
        select qon.quota_order_number_id, qon.quota_order_number_sid,
        string_agg(ga.geographical_area_id, '|' order by ga.geographical_area_id) as exclusions
        from quota_order_number_origin_exclusions qonoe, quota_order_number_origins qono,
        quota_order_numbers qon, geographical_areas ga
        where qono.quota_order_number_origin_sid = qonoe.quota_order_number_origin_sid
        and qon.quota_order_number_sid = qono.quota_order_number_sid
        and ga.geographical_area_sid = qonoe.excluded_geographical_area_sid
        and qon.quota_order_number_id like '05%'
        group by qon.quota_order_number_id, qon.quota_order_number_sid
        order by 1;"""
        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            quota_exclusion = QuotaExclusion()
            quota_exclusion.quota_order_number_id = row[0]
            quota_exclusion.quota_order_number_sid = row[1]
            quota_exclusion.exclusions = row[2]

            self.quota_exclusions.append(quota_exclusion)

        # Get quota definitions
        self.quota_definitions = []

        # This SQL works with all quotas that have origins, however there are a few that have no origins
        sql = """
        select qon.quota_order_number_sid, qon.quota_order_number_id, qd.validity_start_date::text, qd.validity_end_date::text,
        qd.initial_volume,
        qd.measurement_unit_code || ' ' || coalesce(qd.measurement_unit_qualifier_code, '') as unit,
        qd.critical_state, qd.critical_threshold, 'First Come First Served' as quota_type,
        string_agg(distinct qono.geographical_area_id, '|' order by qono.geographical_area_id) as origins, qd.quota_definition_sid
        from quota_order_numbers qon, quota_definitions qd, quota_order_number_origins qono
        where qd.quota_order_number_sid = qon.quota_order_number_sid
        and qon.quota_order_number_sid = qono.quota_order_number_sid
        and qon.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (qon.validity_end_date is null or qon.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        and qd.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (qd.validity_end_date is null or qd.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        and qon.quota_order_number_id like '05%'
        group by qon.quota_order_number_sid, qon.quota_order_number_id, qd.validity_start_date, qd.validity_end_date,
        qd.initial_volume, qd.measurement_unit_code, qd.measurement_unit_qualifier_code,
        qd.critical_state, qd.critical_threshold, qd.quota_definition_sid

        union

        select Null as quota_order_number_sid, m.ordernumber as quota_order_number_id,
        m.validity_start_date::text, m.validity_end_date, Null as initial_volume,
        Null as unit, Null as critical_state, Null as critical_threshold, 'Licensed' as quota_type,
        string_agg(distinct m.geographical_area_id, '|' order by m.geographical_area_id) as origins, Null as quota_definition_sid
        from utils.materialized_measures_real_end_dates m
        where ordernumber like '054%'
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        group by m.ordernumber, m.validity_start_date, m.validity_end_date
        order by 2
        """

        # This SQL works with all quotas, even if they have no origins, however it does not populate the "origins" field
        # Need to know for sure if this matters.
        sql = """
        select qon.quota_order_number_sid, qon.quota_order_number_id, qd.validity_start_date::text, qd.validity_end_date::text,
        qd.initial_volume,
        qd.measurement_unit_code || ' ' || coalesce(qd.measurement_unit_qualifier_code, '') as unit,
        qd.critical_state, qd.critical_threshold, 'First Come First Served' as quota_type,
        '' as origins,
        qd.quota_definition_sid
        from quota_order_numbers qon, quota_definitions qd --, quota_order_number_origins qono
        where qd.quota_order_number_sid = qon.quota_order_number_sid
        and qon.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (qon.validity_end_date is null or qon.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        and qd.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (qd.validity_end_date is null or qd.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        and qon.quota_order_number_id like '05%'
        and qon.quota_order_number_id not like '054%'
        group by qon.quota_order_number_sid, qon.quota_order_number_id, qd.validity_start_date, qd.validity_end_date,
        qd.initial_volume, qd.measurement_unit_code, qd.measurement_unit_qualifier_code,
        qd.critical_state, qd.critical_threshold, qd.quota_definition_sid

        union

        select Null as quota_order_number_sid, m.ordernumber as quota_order_number_id,
        m.validity_start_date::text, m.validity_end_date, Null as initial_volume,
        Null as unit, Null as critical_state, Null as critical_threshold, 'Licensed' as quota_type,
        '' as origins,
        Null as quota_definition_sid
        from utils.materialized_measures_real_end_dates m
        where ordernumber like '054%'
        and m.validity_start_date <= '""" + self.SNAPSHOT_DATE + """'
        and (m.validity_end_date is null or m.validity_end_date > '""" + self.SNAPSHOT_DATE + """')
        group by m.ordernumber, m.validity_start_date, m.validity_end_date
        order by 2
        """

        d = Database()
        rows = d.run_query(sql)
        for row in rows:
            quota_definition = QuotaDefinition()
            quota_definition.quota_order_number_sid = row[0]
            quota_definition.quota_order_number_id = row[1]
            quota_definition.validity_start_date = row[2]
            quota_definition.validity_end_date = row[3]
            quota_definition.initial_volume = row[4]
            quota_definition.unit = row[5]
            quota_definition.critical_state = row[6]
            quota_definition.critical_threshold = row[7]
            quota_definition.quota_type = row[8]
            quota_definition.origins = row[9]
            quota_definition.quota_definition_sid = row[10]

            # Assign the exclusions to the definitions
            for exclusion in self.quota_exclusions:
                if exclusion.quota_order_number_sid == quota_definition.quota_order_number_sid:
                    quota_definition.exclusions = exclusion.exclusions
                    break

            # Assign the commodities to the definitions
            for quota_commodity in self.quota_commodities:
                if quota_commodity.quota_order_number_id == quota_definition.quota_order_number_id:
                    quota_definition.commodities = quota_commodity.commodities
                    break

            self.quota_definitions.append(quota_definition)

        self.end_timer("Getting and writing all quota definitions for CSV export")

    def rebase_chapters(self):
        # Reset the indent of chapters to -1, so that they are
        # omitted from the hierarchy string
        self.start_timer("Rebasing chapters")
        for commodity in self.commodities:
            commodity.get_entity_type()

            # Do not rebase data for the CSV file
            commodity.number_indents_csv = commodity.number_indents

            # Rebase data for working out hierarchical inheritance
            if commodity.significant_digits == 2:
                commodity.number_indents = -1

        self.end_timer("Rebasing chapters")

    def load_to_aws(self, msg, file, aws_path):
        if self.write_to_aws == 1:
            print(msg)
            bucket = AwsBucket()
            ret = bucket.upload_file(file, aws_path)
            return ret
        else:
            return None

    def send_email_message(self, subject, content, attachment_list):
        self.send_mail = int(os.getenv('SEND_MAIL'))
        if self.send_mail == 0:
            return
        s = SendgridMailer(subject, content, attachment_list)
        s.send()

    def start_timer(self, msg):
        self.tic = time.perf_counter()
        # msg = msg.upper() + "\n - Starting"
        msg = msg.upper()
        print(msg)
        self.message_string += msg + "\n"

    def end_timer(self, msg):
        self.toc = time.perf_counter()
        msg = " - Completed in " + \
            "{:.1f}".format(self.toc - self.tic) + " seconds\n"
        print(msg)
        self.message_string += msg + "\n"

    def start_loop_timer(self, msg):
        self.loop_tic = time.perf_counter()
        # msg = msg.upper() + "\n - Starting"
        msg = msg.upper()
        print(msg + "\n")
        self.message_string += msg + "\n"

    def end_loop_timer(self, msg):
        self.loop_toc = time.perf_counter()
        msg = msg.upper() + " - Completed in " + \
            "{:.1f}".format(self.loop_toc - self.loop_tic) + " seconds\n"
        print(msg + "\n")
        self.message_string += msg + "\n"

    def YYYYMMDD(self, d):
        if d is None:
            return "00000000"
        else:
            ret = d.strftime("%Y%m%d")
            return ret

    def HHMMSS(self, d):
        if d is None:
            return "00000000"
        else:
            ret = d.strftime("%H%M%S")
            return ret
