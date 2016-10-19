

import colorsys

def get_N_colors(N, s=0.8, v=0.9):
    HSV_tuples = [(x*1.0/N, s, v) for x in range(N)]
    hex_out = []
    for rgb in HSV_tuples:
        rgb = map(lambda x: int(x*255),colorsys.hsv_to_rgb(*rgb))
        hex_out.append("#"+"".join(map(lambda x: format(x, '02x'),rgb)))
    return hex_out
