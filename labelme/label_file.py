import base64
import io
import json
import os.path as osp

import PIL.Image

from labelme._version import __version__
from labelme.logger import logger
from labelme import PY2
from labelme import QT4
from labelme import utils


class LabelFileError(Exception):
    pass


class LabelFile(object):

    suffix = '.json'

    def __init__(self, filename=None):
        self.shapes = ()
        # self.imagePath = None
        self.image_date1Path = None
        self.image_date2Path = None
        # self.imageData = None
        self.image_date1Data = None
        self.image_date2Data = None #Bad file naming convention
        if filename is not None:
            self.load(filename)
        self.filename = filename

    @staticmethod
    def load_image_file(filename):
        try:
            image_pil = PIL.Image.open(filename)
        except IOError:
            logger.error('Failed opening image file: {}'.format(filename))
            return

        # apply orientation to image according to exif
        image_pil = utils.apply_exif_orientation(image_pil)

        with io.BytesIO() as f:
            ext = osp.splitext(filename)[1].lower()
            if PY2 and QT4:
                format = 'PNG'
            elif ext in ['.jpg', '.jpeg']:
                format = 'JPEG'
            else:
                format = 'PNG'
            image_pil.save(f, format=format)
            f.seek(0)
            return f.read()

    def load_image_pair(filename_date1, filename_date2):
        try:
            image_date1_pil = PIL.Image.open(filename_date1)
            image_date2_pil = PIL.Image.open(filename_date2)
        except IOError:
            logger.error('Failed opening image pair: {} {}'.format(filename_date1, filename_date2))
            return

        # apply orientation to image according to exif
        image_date1_pil = utils.apply_exif_orientation(image_date1_pil)
        image_date2_pil = utils.apply_exif_orientation(image_date2_pil)

        date1_f = io.BytesIO()
        date2_f = io.BytesIO()
        if date1_f and date2_f:
            date1_ext = osp.splitext(filename_date1)[-1].lower()
            date2_ext = osp.splitext(filename_date2)[-1].lower()
            if PY2 and QT4:
                format = 'PNG'
            elif date1_ext in ['.jpg', '.jpeg'] and date2_ext in ['.jpg', '.jpeg']:
                format = 'JPEG'
            else:
                format = 'PNG'
            image_date1_pil.save(date1_f, format=format)
            image_date2_pil.save(date2_f, format=format)
            date1_f.seek(0)
            date2_f.seek(0)
            return date1_f.read(), date2_f.read()

    def load(self, filename):
        keys = [
            'image_date1Data',
            'image_date2Data'
            'image_date1Path',
            'image_date2Path',
            'lineColor',
            'fillColor',
            'shapes',  # polygonal annotations
            'flags',   # image level flags
            'imageHeight',
            'imageWidth',
        ]
        try:
            with open(filename, 'rb' if PY2 else 'r') as f:
                data = json.load(f)
            if data['image_date1Data'] is not None and data['image_date2Data'] is not None:
                image_date1Data = base64.b64decode(data['image_date1Data'])
                image_date2Data = base64.b64decode(data['image_date2Data'])
                if PY2 and QT4:
                    image_date1Data = utils.img_data_to_png_data(image_date1Data)
                    image_date2Data = utils.img_data_to_png_data(image_date2Data)
            else:
                # relative path from label file to relative path from cwd
                image_date1Path = osp.join(osp.dirname(filename), data['image_date1Path'])
                image_date2Path = osp.join(osp.dirname(filename), data['image_date2Path'])
                image_date1Data, image_date2Data = self.load_image_pair(image_date1Path, image_date2Path)
            flags = data.get('flags') or {}
            image_date1Path = data['image_date1Path']
            image_date2Path = data['image_date2Path']
            self._check_image_height_and_width(
                base64.b64encode(image_date1Data).decode('utf-8'),
                data.get('imageHeight'),
                data.get('imageWidth'),
            )
            self._check_image_height_and_width(
                base64.b64encode(image_date2Data).decode('utf-8'),
                data.get('imageHeight'),
                data.get('imageWidth'),
            )
            lineColor = data['lineColor']
            fillColor = data['fillColor']
            shapes = (
                (
                    s['label'],
                    s['points'],
                    s['line_color'],
                    s['fill_color'],
                    s.get('shape_type', 'polygon'),
                    s.get('flags', {}),
                )
                for s in data['shapes']
            )
        except Exception as e:
            raise LabelFileError(e)

        otherData = {}
        for key, value in data.items():
            if key not in keys:
                otherData[key] = value

        # Only replace data after everything is loaded.
        self.flags = flags
        self.shapes = shapes
        self.image_date1Path = image_date1Path
        self.image_date2Path = image_date2Path
        self.image_date1Data = image_date1Data
        self.image_date2Data = image_date2Data
        self.lineColor = lineColor
        self.fillColor = fillColor
        self.filename = filename
        self.otherData = otherData

    @staticmethod
    def _check_image_height_and_width(imageData, imageHeight, imageWidth):
        img_arr = utils.img_b64_to_arr(imageData)
        if imageHeight is not None and img_arr.shape[0] != imageHeight:
            logger.error(
                'imageHeight does not match with imageData or imagePath, '
                'so getting imageHeight from actual image.'
            )
            imageHeight = img_arr.shape[0]
        if imageWidth is not None and img_arr.shape[1] != imageWidth:
            logger.error(
                'imageWidth does not match with imageData or imagePath, '
                'so getting imageWidth from actual image.'
            )
            imageWidth = img_arr.shape[1]
        return imageHeight, imageWidth

    def save(
        self,
        filename,
        shapes,
        image_date1Path,
        image_date2Path,
        imageHeight,
        imageWidth,
        image_date1Data=None,
        image_date2Data=None,
        lineColor=None,
        fillColor=None,
        otherData=None,
        flags=None,
    ):
        if image_date1Data is not None and image_date2Data is not None:
            image_date1Data = base64.b64encode(image_date1Data).decode('utf-8')
            image_date2Data = base64.b64encode(image_date2Data).decode('utf-8')
            imageHeight, imageWidth = self._check_image_height_and_width(
                image_date1Data, imageHeight, imageWidth
            )
            imageHeight, imageWidth = self._check_image_height_and_width(
                image_date2Data, imageHeight, imageWidth
            )
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        data = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            lineColor=lineColor,
            fillColor=fillColor,
            image_date1Path=image_date1Path,
            image_date2Path=image_date2Path,
            image_date1Data=image_date1Data,
            image_date2Data=image_date2Data,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            data[key] = value
        try:
            with open(filename, 'wb' if PY2 else 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def is_label_file(filename):
        return osp.splitext(filename)[1].lower() == LabelFile.suffix
