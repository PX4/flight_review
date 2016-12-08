
class DBData:
    """ simple class that contains information from the DB entry of a single
    log file """
    def __init__(self):
        self.description = ''
        self.feedback = ''
        self.type = 'personal'
        self.wind_speed = -1
        self.rating = ''
        self.video_url = ''

    def windSpeedStr(self):
        return {0: 'Calm', 5: 'Breeze', 8: 'Gale', 10: 'Storm'}.get(self.wind_speed, '')

    def ratingStr(self):
        return {'crash_pilot': 'Crashed (Pilot mistake)',
                'crash_sw_hw': 'Crashed (Software or Hardware issue)',
                'unsatisfactory': 'Unsatisfactory',
                'good': 'Good',
                'great': 'Great!'}.get(self.rating, '')


