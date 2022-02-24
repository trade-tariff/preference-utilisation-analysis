import classes.globals as g


class MeasureExcludedGeographicalArea(object):
    def __init__(self):
        self.measure_sid = None
        self.excluded_geographical_area = None
        self.geographical_area_sid = None
        
        # self.get_description()

    def get_description(self):
        if self.geographical_area_sid is not None:
            self.geographical_area_description = g.app.geographical_areas_friendly[self.geographical_area_sid]
            a = 1