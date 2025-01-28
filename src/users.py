from src.filters import ChangeFilter


class UserInterest:
    def __init__(self, user_id: str, filters: list[ChangeFilter]):
        self.user_id = user_id
        self.filters = filters

    def __repr__(self):
        return "UserInterest(user_id={}, filters={})".format(self.user_id, self.filters)
