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
