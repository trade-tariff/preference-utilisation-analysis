import os
import sys
import time
import json
from pathlib2 import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
import xlsxwriter

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
        self.get_units()
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

    def get_units(self):
        filename = os.path.join(os.getcwd(), "data", "units.json")
        f = open(filename)
        self.units = json.load(f)
        a = 1
    
    def get_filename(self):
        self.file_only = self.MEASURES_FILENAME + "_{dt}.xlsx".format(dt=self.SNAPSHOT_DATE)
        self.filename = os.path.join(self.dated_folder, self.file_only)

        self.geo_file_only = "trade_groups_{dt}.xlsx".format(dt=self.SNAPSHOT_DATE)
        self.geo_filename = os.path.join(self.dated_folder, self.geo_file_only)

    def create_data_extract(self):
        self.get_reference_data()
        # self.get_quota_balances()
        # self.get_quotas()
        # self.assign_quota_balances()
        self.get_commodities()

    def get_commodities(self):
        # Create the Excel document right at the start
        # Also write the table headers
        self.workbook = xlsxwriter.Workbook(self.filename, {'strings_to_urls': False})

        # Standard fields
        self.standard = self.workbook.add_format({'bold': False})
        self.standard.set_font_name("Times New Roman")
        self.standard.set_font_size(10)

        self.standard_right = self.workbook.add_format({'bold': False})
        self.standard_right.set_font_name("Times New Roman")
        self.standard_right.set_align("right")
        self.standard_right.set_font_size(10)

        self.standard_centred = self.workbook.add_format({'bold': False})
        self.standard_centred.set_font_name("Times New Roman")
        self.standard_centred.set_align("center")
        self.standard_centred.set_font_size(10)

        # Bold fields used for header row only
        self.bold = self.workbook.add_format({'bold': True})
        self.bold.set_font_name("Times New Roman")
        self.bold.set_font_size(10)

        self.bold_right = self.workbook.add_format({'bold': True})
        self.bold_right.set_font_name("Times New Roman")
        self.bold_right.set_align("right")
        self.bold_right.set_font_size(10)

        self.bold_centred = self.workbook.add_format({'bold': True})
        self.bold_centred.set_font_name("Times New Roman")
        self.bold_centred.set_align("center")
        self.bold_centred.set_font_size(10)

        self.worksheet = self.workbook.add_worksheet(self.SNAPSHOT_DATE)

        fields = [
            ["CODE", 20, "bold"],
            ["DESCRIPTION", 100, "bold"],
            ["FROM", 20, "bold"],
            ["TO", 20, "bold"],
            ["DUTY", 40, "bold"],
            ["VAT", 20, "bold_centred"],
            ["Add", 10, "bold_centred"],
            ["Pref", 10, "bold_centred"],
            ["LIC", 10, "bold_centred"],
            ["DPO", 10, "bold_centred"],
            ["CAP", 10, "bold_centred"],
            ["Quota", 10, "bold_centred"],
            ["Excise", 10, "bold_centred"],
            ["End", 10, "bold_centred"],
            ["MM", 10, "bold_centred"],
            ["Qty1", 10, "bold_centred"],
            ["Qty2", 10, "bold_centred"],
            ["Qty3", 10, "bold_centred"],
            ["Qty1", 10, "bold_centred"],
            ["Qty2", 10, "bold_centred"],
            ["Qty3", 10, "bold_centred"]
        ]

        col = 0
        for field, column_width, style in (fields):
            column_string = chr(col + 65) + ":" + chr(col + 65)
            self.worksheet.set_column(column_string, column_width)
            if style == "bold_right":
                style = self.bold_right
            elif style == "bold_centred":
                style = self.bold_centred
            else:
                style = self.bold
            self.worksheet.write(0, col, field, style)
            col += 1

        self.row_count = 1
        for i in range(self.start, self.end):
            self.start_loop_timer("Creating data for commodity codes starting with " + str(i))
            self.commodities = []
            self.get_measure_components(i)
            # self.get_measure_conditions(i)
            # self.get_measure_excluded_geographical_areas(i)
            self.get_measures(i)

            self.assign_measure_components_to_measures()
            # self.assign_measure_conditions_to_measures()
            # self.get_condition_strings()
            # self.assign_measure_excluded_geographical_areas()
            # self.get_quota_status()
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
                commodity.validity_start_date = self.DDMMYYYY(row[3])
                commodity.validity_end_date = self.DDMMYYYY(row[4])
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
        self.worksheet.autofilter('A1:U' + str(self.row_count))
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

    def get_quota_status(self):
        for m in self.measures:
            m.get_quota_status()

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
            if commodity.leaf == 1 and commodity.goods_nomenclature_item_id[0:2] != "99":
                # Comm code-related fields
                self.worksheet.write(self.row_count, 0, commodity.goods_nomenclature_item_id, self.standard)
                self.worksheet.write(self.row_count, 1, commodity.hierarchical_description, self.standard)
                self.worksheet.write(self.row_count, 2, commodity.validity_start_date, self.standard)
                self.worksheet.write(self.row_count, 3, commodity.validity_end_date, self.standard)
                
                self.found_mfn = False
                self.add_string = "N"
                self.pref_string = "N"
                self.quota_string = "N"
                self.VAT_string = ""
                self.excise_string = ""
                self.end_use_string = "N"
                self.VATs = []
                self.supp_units = []
                
                for measure in commodity.measures:
                    if measure.measure_sid == 2982964:
                        a = 1
                    # Get the duty string
                    if measure.measure_type_id in ("103", "105"):
                        if self.found_mfn == False:
                            self.worksheet.write(self.row_count, 4, measure.english_duty_string, self.standard)
                            self.found_mfn = True
                        if measure.measure_type_id == "105":
                            self.end_use_string = "Y"
                    
                    # Get the VAT string
                    elif measure.measure_type_id in ("305"):
                        if measure.additional_code == "":
                            self.VATs.append("S")
                        elif measure.additional_code == "VATR":
                            self.VATs.append("R")
                        elif measure.additional_code == "VATZ":
                            self.VATs.append("Z")
                        elif measure.additional_code == "VATE":
                            self.VATs.append("E")
                    
                    # Get ADD (Dumping)
                    elif measure.measure_type_id in ("551", "552", "553", "554"):
                        self.add_string = "Y"
                    
                    # Get pref string
                    elif measure.measure_type_id in ("142", "145"):
                        self.pref_string = "Y"
                    
                    # Get quota string
                    elif measure.measure_type_id in ("122", "123", "143", "146"):
                        self.quota_string = "Y"
                    
                    # Get quota string
                    elif measure.measure_type_id in ("306"):
                        self.excise_string = "Y"
                    
                    # Get supp units
                    elif measure.measure_type_id in ("109", "110", "111"):
                        if measure.english_duty_string != "":
                            self.supp_units.append(measure.english_duty_string)
                        
                self.VAT_string = ", ".join(self.VATs)
                self.qty1 = "000"
                self.qty2 = "000"
                self.qty3 = "000"
                
                self.qty1_clean = ""
                self.qty2_clean = ""
                self.qty3_clean = ""

                if commodity.goods_nomenclature_item_id == "0106110000":
                    a = 1
                    
                has_kgm = False
                for s in self.supp_units:
                    if "KGM" in s:
                        has_kgm = True
                
                if not has_kgm:
                    self.supp_units.insert(0, "KGM")
                    
                self.chief_units = []
                for s in self.supp_units:
                    if s in self.units:
                        self.chief_units.append(self.units[s])
                
                # self.chief_units = sorted(self.chief_units)

                if len(self.chief_units) > 0:
                    self.qty1 = self.chief_units[0]
                    self.qty1_clean = self.supp_units[0]
                if len(self.chief_units) > 1:
                    self.qty2 = self.chief_units[1]
                    self.qty2_clean = self.supp_units[1]
                if len(self.chief_units) > 2:
                    self.qty3 = self.chief_units[2]
                    self.qty3_clean = self.supp_units[2]
                    

                self.worksheet.write(self.row_count, 5, self.VAT_string, self.standard_centred)
                self.worksheet.write(self.row_count, 6, self.add_string, self.standard_centred)
                self.worksheet.write(self.row_count, 7, self.pref_string, self.standard_centred)
                self.worksheet.write(self.row_count, 8, "", self.standard_centred) # LIC
                self.worksheet.write(self.row_count, 9, "", self.standard_centred) # DPO
                self.worksheet.write(self.row_count, 10, "", self.standard_centred) # CAP
                self.worksheet.write(self.row_count, 11, self.quota_string, self.standard_centred)
                self.worksheet.write(self.row_count, 12, self.excise_string, self.standard_centred)
                self.worksheet.write(self.row_count, 13, self.end_use_string, self.standard_centred)
                self.worksheet.write(self.row_count, 14, "", self.standard_centred) # MM
                self.worksheet.write(self.row_count, 15, self.qty1, self.standard_centred) # Qty1
                self.worksheet.write(self.row_count, 16, self.qty2, self.standard_centred) # Qty2
                self.worksheet.write(self.row_count, 17, self.qty3, self.standard_centred) # Qty3
                self.worksheet.write(self.row_count, 18, self.qty1_clean, self.standard_centred) # Qty1
                self.worksheet.write(self.row_count, 19, self.qty2_clean, self.standard_centred) # Qty2
                self.worksheet.write(self.row_count, 20, self.qty3_clean, self.standard_centred) # Qty3

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
        -- and m.measure_type_id not in ('109', '110', '111')
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

    def DDMMYYYY(self, d):
        if d is None:
            return ""
        else:
            ret = d.strftime("%d/%m/%Y")
            return ret

    def HHMMSS(self, d):
        if d is None:
            return "00000000"
        else:
            ret = d.strftime("%H%M%S")
            return ret
