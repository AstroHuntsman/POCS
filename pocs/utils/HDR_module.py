import signal_to_noise as snr
import dither
from astropy import units as u
from astropy.coordinates import SkyCoord
from pocs.utils.config import load_config
config = load_config('snr_config')
def create_imager_array():
    optics = dict()
    cameras = dict()
    filters = dict()
    psfs = dict()
    imagers = dict()
    imagers_list = []

    #Setup imagers
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
                camera_info['resolution']=[int(a) for a in camera_info['resolution'].split(',')]
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

        imagers[name] = snr.Imager(optic = optic, camera = camera, band = filter, num_imagers = imager_info['num_imagers'],\
                                   num_computer = imager_info['num_computer'], PSF = psf)
        
        
        imagers_list.append(imagers[name])
        
    imager_array = snr.ImagerArray(imagers_list)
                  
    return imager_array

imager_array = create_imager_array()

dither_functions = {'dice_9': dither.dither_dice9, 'dice_5': dither.dither_dice5, 'dice_random':dither.dither_random}

def HDR_target_list(ra_dec, name, minimum_magnitude, dither_function = dither.dither_dice9, dither_parameters={'offset': 0.5 *\
                   u.degree}, factor=2, maximum_exptime = 300 * u.second, num_longexp = 1, priority = 100):
    
    if not isinstance(ra_dec, SkyCoord):
        ra_dec = SkyCoord(ra_dec)
        
    try:
        dither = dither_functions[dither_function]
    except KeyError:
        dither = dither_function
        
    explist = imager_array.exposure_time_array(minimum_magnitude, factor, maximum_exptime, num_longexp)
    target_list = []
    position_list = dither_function(ra_dec, **dither_parameters, loop = len(explist))
        
    for i in range(0, len(explist)):
        target = {}
        if ra_dec.obstime is not None:
            target['epoch'] = ra_dec.obstime
        if ra_dec.equinox is not None:
            target['equinox'] = ra_dec.equinox
        if ra_dec.frame.name is not None:
            target['frame'] = ra_dec.frame.name
        target['name'] = name
        target['position'] = position_list[i].to_string('hmsdms')
        target['priority'] = priority
        target['visit'] = {'primary_nexp': 1, 'primary_exptime': explist[i].value}
        target_list.append(target)

    return target_list
                
             
                
            
            
    
    
    
                   



    

    
