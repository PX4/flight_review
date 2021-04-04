""" configuration tables """

#pylint: disable=invalid-name

flight_modes_table = {
    0: ('Manual', '#cc0000'), # red
    1: ('Altitude', '#eecc00'), # yellow
    2: ('Position', '#00cc33'), # green
    10: ('Acro', '#66cc00'), # olive
    14: ('Offboard', '#00cccc'), # light blue
    15: ('Stabilized', '#0033cc'), # dark blue
    16: ('Rattitude', '#ee9900'), # orange

    # all AUTO-modes use the same color
    3: ('Mission', '#6600cc'), # purple
    4: ('Loiter', '#6600cc'), # purple
    5: ('Return to Land', '#6600cc'), # purple
    6: ('RC Recovery', '#6600cc'), # purple
    7: ('Return to groundstation', '#6600cc'), # purple
    8: ('Land (engine fail)', '#6600cc'), # purple
    9: ('Land (GPS fail)', '#6600cc'), # purple
    12: ('Descend', '#6600cc'), # purple
    13: ('Terminate', '#6600cc'), # purple
    17: ('Takeoff', '#6600cc'), # purple
    18: ('Land', '#6600cc'), # purple
    19: ('Follow Target', '#6600cc'), # purple
    20: ('Precision Land', '#6600cc'), # purple
    21: ('Orbit', '#6600cc'), # purple
    }

vtol_modes_table = {
    1: ('Transition', '#cc0000'), # red
    2: ('Fixed-Wing', '#eecc00'), # yellow
    3: ('Multicopter', '#0033cc'), # dark blue
    }

error_labels_table = {
    # the labels (values) have to be capitalized!
    # 'validate_error_labels_and_get_ids' will return an error otherwise
    1: 'Other',
    2: 'Vibration',
    3: 'Airframe-design',
    4: 'Sensor-error',
    5: 'Component-failure',
    6: 'Software',
    7: 'Human-error',
    8: 'External-conditions'
       # Note: when adding new labels, always increase the id, never re-use a lower value
    }

