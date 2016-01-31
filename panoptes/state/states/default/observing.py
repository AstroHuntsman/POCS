def on_enter(event_data):
    """ """
    pan = event_data.model
    pan.say("I'm finding exoplanets!")

    try:
        imgs_info = pan.observatory.observe()
        img_files = [img['img_file'] for img in imgs_info]
    except Exception as e:
        pan.logger.warning("Problem with imaging: {}".format(e))
        pan.say("Hmm, I'm not sure what happened with that exposure.")
    else:
        # Wait for files to exist to finish to set up processing
        try:
            pan.wait_until_files_exist(img_files, transition='analyze')
        except Exception as e:
            pan.logger.error("Problem waiting for images: {}".format(e))
            pan.goto('park')