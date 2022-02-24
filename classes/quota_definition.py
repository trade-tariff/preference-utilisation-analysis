from classes.functions import functions as f


class QuotaDefinition(object):
    def __init__(self):
        self.exclusions = ""
        self.commodities = ""
        self.quota_balances = []
        self.quota_balance = 999999999999

class QuotaExclusion(object):
    def __init__(self):
        pass

class QuotaCommodity(object):
    def __init__(self):
        pass
