from classes.functions import functions as f


class QuotaBalance(object):
    def __init__(self, quota_order_number_id, quota_definition_sid, occurrence_timestamp,
        new_balance, quota_order_number_sid, validity_start_date, validity_end_date):
        self.quota_order_number_id = quota_order_number_id
        self.quota_definition_sid = quota_definition_sid
        self.occurrence_timestamp = occurrence_timestamp
        self.new_balance = new_balance
        self.quota_order_number_sid = quota_order_number_sid
        self.validity_start_date = validity_start_date
        self.validity_end_date = validity_end_date

        a = 1