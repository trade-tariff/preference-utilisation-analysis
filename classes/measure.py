import sys
import classes.globals as g


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
            self.quota_status =  "See RPA"
        else:
            if self.ordernumber in g.app.quota_order_numbers:
                if g.app.quota_order_numbers[self.ordernumber] == 0:
                    self.quota_status = "Exhausted"
                else:
                    self.quota_status = "Open"
            else:
                self.quota_status = "Exhausted"
