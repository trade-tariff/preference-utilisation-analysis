class MeasureCondition(object):
    def __init__(self):
        self.measure_sid = None

    def get_condition_string(self):
        # Set action code to empty string if it is empty
        if self.action_code is None:
            self.action_code = ""

        s = "condition:"
        s += self.condition_code + ","
        if self.certificate_type_code != "":
            s += "certificate:" + self.certificate_type_code + self.certificate_code + ","
        s += "action:" + self.action_code
        self.condition_string = s

        if self.certificate_type_code != "":
            self.condition_string_stw = self.certificate_type_code + self.certificate_code
        else:
            self.condition_string_stw = ""
