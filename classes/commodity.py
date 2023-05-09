import re
from unidecode import unidecode
import classes.globals as g


class Commodity(object):
    def __init__(self):
        self.goods_nomenclature_sid = None
        self.goods_nomenclature_item_id = None
        self.productline_suffix = None
        self.description = ""
        self.number_indents = None
        self.leaf = None
        self.hierarchy = []
        self.hierarchy_string = ""
        self.measures = []
        self.hierarchy_sids = []
        self.primary_third_country_duty = None
        self.supplementary_unit_string = ""

    def cleanse_description(self):
        if self.description is None:
            self.description = g.app.PLACEHOLDER_FOR_EMPTY_DESCRIPTIONS
        else:
            self.description = self.description.strip()
            if self.description == "":
                self.description = g.app.PLACEHOLDER_FOR_EMPTY_DESCRIPTIONS

        self.description = self.description.replace('"', "'")
        self.description = re.sub(r"<br>", " ", self.description)
        self.description = re.sub(r"\r", " ", self.description)
        self.description = re.sub(r"\n", " ", self.description)
        self.description = re.sub(r"[ ]{2,10}", " ", self.description)
        self.description = unidecode(self.description)

    def get_entity_type(self):
        # Get the entity type - Chapter, Heading, Heading / commodity, Commodity
        if self.significant_digits == 2:
            self.entity_type = "Chapter"
        elif self.significant_digits == 4:
            if self.leaf == 1:
                self.entity_type = "Heading / commodity"
            else:
                self.entity_type = "Heading"
        else:
            self.entity_type = "Commodity"

    def apply_commodity_inheritance(self):
        self.measure_sids = []
        for m in self.measures:
            self.measure_sids.append(m.measure_sid)

        for commodity in self.hierarchy:
            for measure in commodity.measures:
                if measure.measure_sid not in self.measure_sids:
                    self.measures.append(measure)
                    self.measure_sids.append(measure.measure_sid)

    def sort_measures(self):
        self.measures.sort(key=lambda x: (x.additional_code_id is None, x.additional_code_id), reverse=False)
        self.measures.sort(key=lambda x: (x.additional_code_type_id is None, x.additional_code_type_id), reverse=False)
        self.measures.sort(key=lambda x: (x.ordernumber is None, x.ordernumber), reverse=False)
        self.measures.sort(key=lambda x: x.geographical_area_id, reverse=False)
        self.measures.sort(key=lambda x: x.measure_type_id, reverse=False)

    def get_supplementary_unit(self):
        self.supplementary_unit_string = ""
        for measure in self.measures:
            if measure.geographical_area_id in ["1011", "1008"]:
                if measure.measure_type_id in ["109", "110"]:
                    # print("Found a supp unit on commodity {commodity_code}".format(commodity_code=self.goods_nomenclature_item_id))
                    self.supplementary_unit_string = measure.english_duty_string

    def count_103s(self):
        self.additional_code_priority_list = [
            "",
            "2501",
            "2601",
            "2701",
            "2500",
            "2600",
            "2700",
            "2702",
            "2704"
        ]
        suspension_code_types = ["2500", "2600", "2700"]
        mfn_code_types = ["2501", "2601", "2701", "2702", "2704"]
        self.count_103 = 0
        self.count_mfn = 0
        self.count_sus = 0
        self.count_naked = 0
        for measure in self.measures:
            if measure.geographical_area_id in ["1011", "1008"]:
                if measure.measure_type_id in ["103", "105"]:

                    for additional_code in self.additional_code_priority_list:
                        if measure.additional_code == additional_code:
                            self.primary_third_country_duty = measure
                            break

                    self.count_103 += 1
                    if measure.additional_code in mfn_code_types:
                        self.count_mfn += 1
                    elif measure.additional_code in suspension_code_types:
                        self.count_sus += 1
                    else:
                        self.count_naked += 1
