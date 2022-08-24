""" VTOL tailsitter attitude and rate correction code """

from scipy.spatial.transform import Rotation as Rot
import numpy as np

def tailsitter_orientation(ulog, vtol_states):
    """
    corrections for VTOL tailsitter attitude and rates
    tailsitter uses 90 degree rotation in pitch which is hardcoded in
    rather than consistently reported in estimated and setpoint
    use setpoint values as ground truth here and correct estimated by 90 degrees
    rates also need yaw and roll swapped with a -1 on roll axis
    """
    # correct attitudes for VTOL tailsitter in FW mode
    try:
        cur_dataset = ulog.get_dataset('vehicle_attitude')
        quat_0 = cur_dataset.data['q[0]']
        quat_1 = cur_dataset.data['q[1]']
        quat_2 = cur_dataset.data['q[2]']
        quat_3 = cur_dataset.data['q[3]']
        quat_t = cur_dataset.data['timestamp']

        rotations = Rot.from_quat(np.transpose(np.asarray([quat_0, quat_1, quat_2, quat_3])))
        rpy = rotations.as_euler('xyz', degrees=True)
        # rotate by -90 degrees pitch in quaternion form to avoid singularity
        fw_rotation = Rot.from_euler('y', -90, degrees=True)
        rpy_fw = (fw_rotation*rotations).as_euler('xyz', degrees=True)

        # convert out into separate variables
        roll = np.deg2rad(rpy[:, 2])
        pitch = np.deg2rad(-1*rpy[:, 1])
        yaw = -180-rpy[:, 0]
        yaw[yaw > 180] = yaw[yaw > 180]-360
        yaw[yaw < -180] = yaw[yaw < -180]+360
        yaw = np.deg2rad(yaw)

        roll_fw = np.deg2rad(rpy_fw[:, 2])
        pitch_fw = np.deg2rad(-1*rpy_fw[:, 1])
        yaw_fw = -180-rpy_fw[:, 0]
        yaw_fw[yaw_fw > 180] = yaw_fw[yaw_fw > 180]-360
        yaw_fw[yaw_fw < -180] = yaw_fw[yaw_fw < -180]+360
        yaw_fw = np.deg2rad(yaw_fw)

        # temporary variables for storing VTOL states
        is_vtol_fw = False
        fw_start = np.nan
        fw_end = np.nan

        for i in vtol_states:
        # states: 1=transition, 2=FW, 3=MC
        # if in FW mode then used FW conversions
            if is_vtol_fw:
                fw_end = i[0]
                roll[np.logical_and(quat_t > fw_start, quat_t < fw_end)] = \
                                roll_fw[np.logical_and(quat_t > fw_start, quat_t < fw_end)]
                pitch[np.logical_and(quat_t > fw_start, quat_t < fw_end)] = \
                                pitch_fw[np.logical_and(quat_t > fw_start, quat_t < fw_end)]
                yaw[np.logical_and(quat_t > fw_start, quat_t < fw_end)] = \
                                yaw_fw[np.logical_and(quat_t > fw_start, quat_t < fw_end)]
                is_vtol_fw = False
            if i[1] == 2:
                fw_start = i[0]
                is_vtol_fw = True

        # if flight ended as FW, convert the final data segment to FW
        if is_vtol_fw:
            roll[quat_t > fw_start] = roll_fw[quat_t > fw_start]
            pitch[quat_t > fw_start] = pitch_fw[quat_t > fw_start]
            yaw[quat_t > fw_start] = yaw_fw[quat_t > fw_start]

        vtol_attitude = {'roll': roll, 'pitch': pitch, 'yaw': yaw}

    except (KeyError, IndexError) as error:
        vtol_attitude = {'roll': None, 'pitch': None, 'yaw': None}

    # correct angular rates for VTOL tailsitter in FW mode
    try:
        cur_dataset = ulog.get_dataset('vehicle_angular_velocity')
        w_r = cur_dataset.data['xyz[0]']
        w_p = cur_dataset.data['xyz[1]']
        w_y = cur_dataset.data['xyz[2]']
        w_t = cur_dataset.data['timestamp']

        # fw rates (roll and yaw swap, roll is negative axis)
        w_r_fw = w_y*-1
        w_y_fw = w_r*1 # *1 to get python to copy not reference
        # temporary variables for storing VTOL states
        is_vtol_fw = False
        fw_start = np.nan
        fw_end = np.nan

        for i in vtol_states:
        # states: 1=transition, 2=FW, 3=MC
        # if in FW mode then used FW conversions
            if is_vtol_fw:
                fw_end = i[0]
                w_r[np.logical_and(w_t > fw_start, w_t < fw_end)] = \
                                w_r_fw[np.logical_and(w_t > fw_start, w_t < fw_end)]
                w_y[np.logical_and(w_t > fw_start, w_t < fw_end)] = \
                                w_y_fw[np.logical_and(w_t > fw_start, w_t < fw_end)]
                is_vtol_fw = False
            if i[1] == 2:
                fw_start = i[0]
                is_vtol_fw = True

        # if flight ended as FW, convert the final data segment to FW
        if is_vtol_fw:
            w_r[quat_t > fw_start] = w_r_fw[quat_t > fw_start]
            w_y[quat_t > fw_start] = w_y_fw[quat_t > fw_start]

        vtol_rates = {'roll': w_r, 'pitch': w_p, 'yaw': w_y}

    except (KeyError, IndexError) as error:
        vtol_rates = {'roll': None, 'pitch': None, 'yaw': None}

    return [vtol_attitude, vtol_rates]
