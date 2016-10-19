
def print_ulog_info(ulog):
    print('System: {:}'.format(ulog.msg_info_dict['sys_name']))
    if 'ver_hw' in ulog.msg_info_dict:
        print('Hardware: {:}'.format(ulog.msg_info_dict['ver_hw']))
    if 'ver_sw' in ulog.msg_info_dict:
        print('Software Version: {:}'.format(ulog.msg_info_dict['ver_sw']))
    # dropouts
    dropout_durations = [ dropout.duration for dropout in ulog.dropouts]
    if len(dropout_durations) > 0:
        total_duration = sum(dropout_durations) / 1000
        if total_duration > 5:
            total_duration_str = '{:.0f}'.format(total_duration)
        else:
            total_duration_str = '{:.2f}'.format(total_duration)
        print('Dropouts: {:} ({:} s)'.format(
            len(dropout_durations), total_duration_str))

    # logging duration
    m, s = divmod(int((ulog.last_timestamp - ulog.start_timestamp)/1e6), 60)
    h, m = divmod(m, 60)
    print('Logging duration: {:d}:{:02d}:{:02d}'.format( h, m, s))
