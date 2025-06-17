
'''
Configuration options for the run module, including file extensions and EXIF tag mappings.
'''

# Determines the minimum number of photos required to create an event folder when restructuring folders.
EVENT_FOLDER_THRESHOLD = 10

IMAGE_EXTENSIONS = [
    '.jpg', '.jpeg', '.jpe', '.jif', '.jfif', '.jfi',
    '.png', '.apng',
    '.tiff', '.tif',
    '.heic', '.heif',
    '.bmp', '.dib',
    '.gif',
    '.webp',
    '.pbm', '.pgm', '.ppm', '.pnm',
    '.svg', '.svgz',
    '.ico', '.cur',
    '.emf', '.wmf',
    '.ras', '.sun', '.im', '.pcx', '.xbm', '.xpm'
]
RAW_EXTENSIONS = [
    '.cr2',  # Canon
    '.cr3',  # Canon
    '.nef',  # Nikon
    '.nrw',  # Nikon
    '.arw',  # Sony
    '.srf',  # Sony
    '.sr2',  # Sony
    '.rw2',  # Panasonic
    '.orf',  # Olympus
    '.pef',  # Pentax
    '.ptx',  # Pentax
    '.dng',  # Adobe Digital Negative
    '.raf',  # Fujifilm
    '.raw',  # Various
    '.rwl',  # Leica
    '.rwz',  # Leica
    '.k25',  # Kodak
    '.kdc',  # Kodak
    '.erf',  # Epson
    '.mrw',  # Minolta
    '.mef',  # Mamiya
    '.mos',  # Leaf
    '.iiq',  # Phase One
    '.3fr',  # Hasselblad
    '.fff',  # Imacon/Hasselblad
    '.srw',  # Samsung
    '.bay',  # Casio
    '.x3f',  # Sigma
    '.cap',  # Phase One
    '.iiq',  # Phase One
    '.mdc',  # Minolta
    '.tif',  # Some cameras use TIFF as RAW
    '.heic', # Some modern cameras/phones
    '.heif'  # Some modern cameras/phones
]
VIDEO_EXTENSIONS = [
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.mts', '.m2ts', '.3gp', '.webm',
    '.flv', '.f4v', '.f4p', '.f4a', '.f4b',  # Flash video
    '.mpg', '.mpeg', '.mpe', '.mpv', '.mp2', '.m2v',  # MPEG
    '.ts', '.vob', '.mxf', '.roq', '.nsv',  # Misc
    '.ogv', '.ogg',  # Ogg
    '.rm', '.rmvb',  # RealMedia
    '.asf', '.asx',  # Advanced Streaming Format
    '.divx',  # DivX
    '.dv',  # Digital Video
    '.amv',  # Anime Music Video
    '.drc',  # Dirac
    '.mng',  # Multiple-image Network Graphics
    '.qt',  # QuickTime
    '.yuv',  # YUV
    '.svi',  # Samsung video
    '.3g2',  # 3GPP2
    '.m4v',  # Apple video
    '.skm',  # Samsung video
    '.trp',  # HD video
    '.vob',  # DVD Video
    '.wtv',  # Windows Recorded TV Show
    '.mve',  # Interplay MVE
    '.ogm',  # OGM
    '.bik',  # Bink Video
    '.iso'   # Disc image (sometimes used for video)
]
EXIF_TAG_MAP = {
    "ImageWidth": "Exif.Image.ImageWidth",
    "ImageLength": "Exif.Image.ImageLength",
    "Make": "Exif.Image.Make",
    "Model": "Exif.Image.Model",
    "Software": "Exif.Image.Software",
    "Orientation": "Exif.Image.Orientation",
    "DateTime": "Exif.Image.DateTime",
    "YCbCrPositioning": "Exif.Image.YCbCrPositioning",
    "XResolution": "Exif.Image.XResolution",
    "YResolution": "Exif.Image.YResolution",
    "ResolutionUnit": "Exif.Image.ResolutionUnit",
    "ExifVersion": "Exif.Photo.ExifVersion",
    "ComponentsConfiguration": "Exif.Photo.ComponentsConfiguration",
    "ShutterSpeedValue": "Exif.Photo.ShutterSpeedValue",
    "DateTimeOriginal": "Exif.Photo.DateTimeOriginal",
    "DateTimeDigitized": "Exif.Photo.DateTimeDigitized",
    "ApertureValue": "Exif.Photo.ApertureValue",
    "BrightnessValue": "Exif.Photo.BrightnessValue",
    "ExposureBiasValue": "Exif.Photo.ExposureBiasValue",
    "MaxApertureValue": "Exif.Photo.MaxApertureValue",
    "SubjectDistance": "Exif.Photo.SubjectDistance",
    "MeteringMode": "Exif.Photo.MeteringMode",
    "Flash": "Exif.Photo.Flash",
    "FocalLength": "Exif.Photo.FocalLength",
    "ColorSpace": "Exif.Photo.ColorSpace",
    "ExifImageWidth": "Exif.Photo.PixelXDimension",
    "ExifImageHeight": "Exif.Photo.PixelYDimension",
    "SceneCaptureType": "Exif.Photo.SceneCaptureType",
    "OffsetTime": "Exif.Photo.OffsetTime",
    "OffsetTimeOriginal": "Exif.Photo.OffsetTimeOriginal",
    "OffsetTimeDigitized": "Exif.Photo.OffsetTimeDigitized",
    "SubsecTime": "Exif.Photo.SubSecTime",
    "SubsecTimeOriginal": "Exif.Photo.SubSecTimeOriginal",
    "SubsecTimeDigitized": "Exif.Photo.SubSecTimeDigitized",
    "SensingMethod": "Exif.Photo.SensingMethod",
    "ExposureTime": "Exif.Photo.ExposureTime",
    "FNumber": "Exif.Photo.FNumber",
    "SceneType": "Exif.Photo.SceneType",
    "ExposureProgram": "Exif.Photo.ExposureProgram",
    "CustomRendered": "Exif.Photo.CustomRendered",
    "ISOSpeedRatings": "Exif.Photo.ISOSpeedRatings",
    "ExposureMode": "Exif.Photo.ExposureMode",
    "FlashPixVersion": "Exif.Photo.FlashPixVersion",
    "WhiteBalance": "Exif.Photo.WhiteBalance",
    "LensMake": "Exif.Photo.LensMake",
    "LensModel": "Exif.Photo.LensModel",
    "DigitalZoomRatio": "Exif.Photo.DigitalZoomRatio",
    "FocalLengthIn35mmFilm": "Exif.Photo.FocalLengthIn35mmFilm",
    "Contrast": "Exif.Photo.Contrast",
    "Saturation": "Exif.Photo.Saturation",
    "Sharpness": "Exif.Photo.Sharpness",
    "SubjectDistanceRange": "Exif.Photo.SubjectDistanceRange",
    "CompositeImage": "Exif.Photo.CompositeImage",
    "UserComment": "Exif.Photo.UserComment",
    "GPSLatitudeRef": "Exif.GPSInfo.GPSLatitudeRef",
    "GPSLatitude": "Exif.GPSInfo.GPSLatitude",
    "GPSLongitudeRef": "Exif.GPSInfo.GPSLongitudeRef",
    "GPSLongitude": "Exif.GPSInfo.GPSLongitude",
    "GPSAltitudeRef": "Exif.GPSInfo.GPSAltitudeRef",
    "GPSAltitude": "Exif.GPSInfo.GPSAltitude",
    "GPSTimeStamp": "Exif.GPSInfo.GPSTimeStamp",
    "GPSSatellites": "Exif.GPSInfo.GPSSatellites",
    "GPSStatus": "Exif.GPSInfo.GPSStatus",
    "GPSMeasureMode": "Exif.GPSInfo.GPSMeasureMode",
    "GPSDOP": "Exif.GPSInfo.GPSDOP",
    "GPSSpeedRef": "Exif.GPSInfo.GPSSpeedRef",
    "GPSSpeed": "Exif.GPSInfo.GPSSpeed",
    "GPSTrackRef": "Exif.GPSInfo.GPSTrackRef",
    "GPSTrack": "Exif.GPSInfo.GPSTrack",
    "GPSImgDirectionRef": "Exif.GPSInfo.GPSImgDirectionRef",
    "GPSImgDirection": "Exif.GPSInfo.GPSImgDirection",
    "GPSMapDatum": "Exif.GPSInfo.GPSMapDatum",
    "GPSDestLatitudeRef": "Exif.GPSInfo.GPSDestLatitudeRef",
    "GPSDestLatitude": "Exif.GPSInfo.GPSDestLatitude",
    "GPSDestLongitudeRef": "Exif.GPSInfo.GPSDestLongitudeRef",
    "GPSDestLongitude": "Exif.GPSInfo.GPSDestLongitude",
    "GPSDestBearingRef": "Exif.GPSInfo.GPSDestBearingRef",
    "GPSDestBearing": "Exif.GPSInfo.GPSDestBearing",
    "GPSDestDistanceRef": "Exif.GPSInfo.GPSDestDistanceRef",
    "GPSDestDistance": "Exif.GPSInfo.GPSDestDistance",
    "GPSProcessingMethod": "Exif.GPSInfo.GPSProcessingMethod",
    "GPSAreaInformation": "Exif.GPSInfo.GPSAreaInformation",
    "GPSDateStamp": "Exif.GPSInfo.GPSDateStamp",
    "GPSDifferential": "Exif.GPSInfo.GPSDifferential",
    "GPSHPositioningError": "Exif.GPSInfo.GPSHPositioningError"
}
