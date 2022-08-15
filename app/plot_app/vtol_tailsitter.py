# VTOL tailsitter attitude and rate correction code
# tailsitter uses 90 degree rotation in pitch which is hardcoded in rather than consistently reported in estimated and setpoint
# use setpoint values as ground truth here and correct estimated by 90 degrees

from scipy.spatial.transform import Rotation as Rot
import numpy as np

def correct_tailsitter_attitude_and_rates(data,vtol_states):

    for d in data:
        if d.name == 'vehicle_attitude':
            q0 = d.data["q[0]"]
            q1 = d.data["q[1]"]
            q2 = d.data["q[2]"]
            q3 = d.data["q[3]"]
            qt = d.data["timestamp"]
        if d.name == 'vehicle_angular_velocity':
            w_r = d.data["xyz[0]"]
            w_p = d.data["xyz[1]"]
            w_y = d.data["xyz[2]"]
            w_t = d.data["timestamp"]

    rotations = Rot.from_quat(np.transpose(np.asarray([q0,q1,q2,q3])))
    RPY = rotations.as_euler('xyz',degrees=True)
    # rotate by -90 degrees pitch in quaternion form to avoid singularity
    FW_rotation = Rot.from_euler('y',-90,degrees=True)
    RPY_FW = (FW_rotation*rotations).as_euler('xyz',degrees=True)

    # convert out into separate variables
    roll = np.deg2rad(RPY[:,2])
    pitch = np.deg2rad(-1*RPY[:,1])
    yaw = -180-RPY[:,0]
    yaw[yaw>180]=yaw[yaw>180]-360
    yaw[yaw<-180]=yaw[yaw<-180]+360
    yaw = np.deg2rad(yaw)

    roll_fw = np.deg2rad(RPY_FW[:,2])
    pitch_fw = np.deg2rad(-1*RPY_FW[:,1])
    yaw_fw = -180-RPY_FW[:,0]
    yaw_fw[yaw_fw>180]=yaw_fw[yaw_fw>180]-360
    yaw_fw[yaw_fw<-180]=yaw_fw[yaw_fw<-180]+360
    yaw_fw = np.deg2rad(yaw_fw)

    # fw rates (roll and yaw swap, roll is negative axis)
    w_r_fw = w_y*-1
    w_p_fw = w_p
    w_y_fw = w_r

    # temporary variables for storing VTOL states
    is_FW = False
    FW_start = np.nan
    FW_end = np.nan

    for i in vtol_states:
    # states: 1=transition, 2=FW, 3=MC
    # if in FW mode then used FW conversions 
        if is_FW:
            FW_end = i[0]
            roll[np.logical_and(qt>FW_start,qt<FW_end)] = roll_fw[np.logical_and(qt>FW_start,qt<FW_end)]
            pitch[np.logical_and(qt>FW_start,qt<FW_end)] = pitch_fw[np.logical_and(qt>FW_start,qt<FW_end)]
            yaw[np.logical_and(qt>FW_start,qt<FW_end)] = yaw_fw[np.logical_and(qt>FW_start,qt<FW_end)]
            w_r[np.logical_and(w_t>FW_start,w_t<FW_end)] = w_r_fw[np.logical_and(w_t>FW_start,w_t<FW_end)]

            is_FW = False
        if i[1] == 2:
            FW_start = i[0]
            is_FW = True

    # if flight ended as FW, convert the final data segment to FW
    if is_FW:
        roll[qt>FW_start] = roll_fw[qt>FW_start]
        pitch[qt>FW_start] = pitch_fw[qt>FW_start]
        yaw[qt>FW_start] = yaw_fw[qt>FW_start]
        w_r[qt>FW_start] = w_r_fw[qt>FW_start]
        w_p[qt>FW_start] = w_p_fw[qt>FW_start]
        w_y[qt>FW_start] = w_y_fw[qt>FW_start]

    RPY = {'roll': roll, 'pitch': pitch, 'yaw': yaw}
    rates = {'roll': w_r, 'pitch': w_p, 'yaw': w_y} 

    return [RPY, rates]
