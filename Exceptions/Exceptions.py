class ImageLoadFailed(Exception):
    """A stub"""
    def __init__(self, imageName, path, target, msg=None):
        if msg is None:
            msg = "An error occured when loading the image"
        super(ImageLoadFailed, self).__init__(msg)
        self.imageName = imageName
