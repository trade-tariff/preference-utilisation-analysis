import sys
from datetime import datetime, timedelta, date
import classes.globals as g
from classes.database import Database


class Measure(object):
    def __init__(self):
        self.english_duty_string = ""
        self.additional_code_description = ""
        self.measure_components = []
        self.measure_conditions = []
        self.footnotes = []
        self.measure_excluded_geographical_areas = []
        self.measure_excluded_geographical_areas_string = ""
        self.measure_excluded_geographical_area_descriptions_string = ""
        self.footnotes_string = ""
        self.regulation_url = ""

    def get_import_export(self):
        if self.trade_movement_code == 0:
            self.is_import = True
            self.is_export = False
        if self.trade_movement_code == 1:
            self.is_import = False
            self.is_export = True
        else:
            self.is_import = True
            self.is_export = True

    def create_measure_duties(self):
        for mc in self.measure_components:
            self.english_duty_string += mc.english_component_definition

    def get_additional_code_description(self):
        if self.additional_code_sid is not None:
            self.additional_code_description = g.app.additional_codes_friendly[self.additional_code_sid]

    def get_geographical_area_description(self):
        if self.geographical_area_sid is not None:
            self.geographical_area_description = g.app.geographical_areas_friendly[self.geographical_area_sid]

    def get_geographical_area_exclusions(self):
        if len(self.measure_excluded_geographical_areas) > 0:
            self.measure_excluded_geographical_areas_string = "|".join(str(mega.excluded_geographical_area) for mega in self.measure_excluded_geographical_areas)
            self.measure_excluded_geographical_area_descriptions_string = "|".join(str(mega.geographical_area_description) for mega in self.measure_excluded_geographical_areas)

    def get_regulation_url(self):
        if self.measure_generating_regulation_id in g.app.base_regulations:
            self.regulation_url = g.app.base_regulations[self.measure_generating_regulation_id]
        else:
            self.regulation_url = ""

    def get_condition_string(self):
        self.condition_string = "|".join(str(mc.condition_string) for mc in self.measure_conditions)

    def get_footnote_string(self):
        if len(self.footnotes) > 0:
            self.footnotes_string = "|".join(str(f.footnote) for f in self.footnotes)

    def get_quota_status(self):
        self.quota_status = ""
        if self.ordernumber == "" or self.ordernumber is None:
            self.quota_status = ""
        elif self.ordernumber[0:3] == "054":
            self.quota_status = "See RPA"
        else:
            if self.ordernumber in g.app.quota_order_numbers:
                if g.app.quota_order_numbers[self.ordernumber] == 0:
                    self.quota_status = "Exhausted"
                else:
                    self.quota_status = "Open"
            else:
                self.quota_status = "Exhausted"

    def check_exhausted(self):
        # This checks all exhausted quotas to see if they have a comparable definition against them
        # If they do not, then they need to be set to "Open", as they cannot possibly be exhausted
        # measure.validity_start_date = row[18]
        # measure.validity_end_date = row[19]

        if self.quota_status == "Exhausted":
            current_year = str(date.today().year)

            # Set the validity of the measure itself: if it is not enddated (infinite), then set the measure end date to the end of the current year
            if self.validity_end_date == "" or self.validity_end_date is None:
                m_end = current_year + "-12-31"
            else:
                m_end = self.validity_end_date[0:10]

            m_start = self.validity_start_date[0:10]

            a = type(self.validity_start_date)
            sql = """
            select validity_start_date::varchar, validity_end_date::varchar
            from quota_definitions qd
            where quota_order_number_id = %s
            order by validity_start_date
            """
            d = Database()
            params = [
                self.ordernumber
            ]
            rows = d.run_query(sql, params)
            definitions = []
            if rows:
                for row in rows:
                    d_start = row[0][0:10]
                    d_end = row[1][0:10]
                    d = Definition(d_start, d_end)
                    definitions.append(d)

                # Conjoin the definitions that are immediately contiguous
                for i in range(0, len(definitions) - 1):
                    d1 = definitions[i]
                    d2 = definitions[i + 1]
                    d1_end = datetime.strptime(d1.validity_end_date, "%Y-%m-%d")
                    d2_start = datetime.strptime(d2.validity_start_date, "%Y-%m-%d")
                    delta = d2_start - d1_end
                    if delta.days == 1:
                        d1.mark_for_deletion = True
                        d2.validity_start_date = d1.validity_start_date

                # And then delete any that are marked for deletion
                for i in range(len(definitions) - 1, -1, -1):
                    d = definitions[i]
                    if d.mark_for_deletion:
                        definitions.pop(i)

                # Finally, compare the extent of the measure with the extents of the quota definitions
                enclosed = False
                for d in definitions:
                    if d.validity_start_date <= g.app.SNAPSHOT_DATE and d.validity_end_date >= g.app.SNAPSHOT_DATE:
                        enclosed = True
                        break

                if not enclosed:
                    self.quota_status = "Invalid"
            else:
                # If there are no definitions at all, set the quota status to "Open" instead
                self.quota_status = "Invalid"


class Definition(object):
    def __init__(self, validity_start_date, validity_end_date):
        self.validity_start_date = validity_start_date
        self.validity_end_date = validity_end_date
        self.mark_for_deletion = False
