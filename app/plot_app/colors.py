""" color helper functions """

#pylint: disable=invalid-name

import colorsys

def get_N_colors(N, s=0.8, v=0.9):
    """ get N distinct colors as a list of hex strings """
    HSV_tuples = [(x*1.0/N, s, v) for x in range(N)]
    hex_out = []
    for rgb in HSV_tuples:
        rgb = map(lambda x: int(x*255), colorsys.hsv_to_rgb(*rgb))
        hex_out.append("#"+"".join(map(lambda x: format(x, '02x'), rgb)))
    return hex_out

def HTML_color_to_RGB(html_color):
    """ convert a HTML string color (eg. '#4422aa') into an RGB list (range 0-255)
    """
    if html_color[0] == '#': html_color = html_color[1:]
    r, g, b = html_color[:2], html_color[2:4], html_color[4:]
    return [int(n, 16) for n in (r, g, b)]

