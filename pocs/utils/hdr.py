from astropy import units as u
from astropy.coordinates import SkyCoord
from pocs.utils import random_dither
from pocs.utils import signal_to_noise as snr
from pocs.utils.config import load_config
from warnings import warn

dither_functions = {'dice_9': random_dither.dither_dice9, 'dice_5': random_dither.dither_dice5}


def create_imager_array():
    config = load_config('performance')

    optics = dict()
    cameras = dict()
    filters = dict()
    psfs = dict()
    imagers_list = []

    # Setup imagers
    for imager_info in config['imagers']:
        name = imager_info['name']
        optic_name = imager_info['optic']
        try:
            # Try to get from cache
            optic = optics[optic_name]
        except KeyError:
            # Create optic from this imager
            optic_info = config['optics'][optic_name]
            optic = snr.Optic(**optic_info)

            # Put in cache
            optics[optic_name] = optic
            camera_name = imager_info['camera']
        try:
            # Try to get from cache
            camera = cameras[camera_name]
        except KeyError:
            # Create camera for this imager
            camera_info = config['cameras'][camera_name]
            if type(camera_info['resolution']) == str:
                camera_info['resolution'] = [int(a) for a in camera_info['resolution'].split(',')]
            camera = snr.Camera(**camera_info)

            # Put in cache
            cameras[camera_name] = camera

        filter_name = imager_info['filter']
        try:
            # Try to get from cache
            filter = filters[filter_name]
        except KeyError:
            # Create optic from this imager
            filter_info = config['filters'][filter_name]
            filter = snr.Filter(**filter_info)

            # Put in cache
            filters[filter_name] = filter

        psf_name = imager_info['psf']
        try:
            # Try to get from cache
            psf = psfs[psf_name]
        except KeyError:
            # Create optic from this imager
            psf_info = config['psfs'][psf_name]
            psf = snr.Moffat_PSF(**psf_info)

            # Put in cache
            psfs[psf_name] = psf

        imager = snr.Imager(optic, camera, filter, imager_info.get(
            'num_imagers', 1), imager_info.get('num_computer', 1), psf)
        imagers_list.append(imager)
    imager_array = snr.ImagerArray(imagers_list)
    return imager_array


def get_hdr_target_list(imager_array=None, coords=None, name=None, minimum_magnitude=10 * u.ABmag, num_longexp=1,
                        dither_function='dice_9',
                        dither_parameters={'big_offset': 0.5 * u.degree, 'small_offset': 0.1 * u.degree}, factor=2,
                        maximum_exptime=300 * u.second, priority=100, maximum_magnitude=None):
    if not isinstance(coords, SkyCoord):
        coords = SkyCoord(coords)

    try:
        dither = dither_functions[dither_function]
    except KeyError:
        warn("Invalid dither given: {}".format(dither_function))

    explist = imager_array.exposure_time_array(
        minimum_magnitude=minimum_magnitude,
        num_longexp=num_longexp,
        factor=factor,
        maximum_exptime=maximum_exptime,
        maximum_magnitude=maximum_magnitude)

    target_list = []
    position_list = dither(coords, dither_parameters['big_offset'], loop=len(explist))

    for i in range(0, len(explist)):
        target = {}
        if coords.obstime is not None:
            target['epoch'] = coords.obstime
        if coords.equinox is not None:
            target['equinox'] = coords.equinox
        target['frame'] = coords.frame.name
        target['name'] = name
        target['position'] = position_list[i].to_string('hmsdms')
        target['priority'] = priority
        target['visit'] = {'primary_nexp': 1, 'primary_exptime': explist[i].value}
        target_list.append(target)

    return target_list
