# -*- coding: utf-8 -*-
"""
Created on Sun Sep 24 22:21:25 2017

@author: Alex
"""

import cv2
import numpy as np
import nibabel as nib
from matplotlib import pyplot as plt

def subsample(analyze_img_path, substep=4, lowfreqPercent=.04):
    """
    Subsamples an MRI image in Analyze 7.5 format
    Note: must have .hdr file

    Parameters
    ------------
    analyze_img_path : str
        The path to the Analyze image path (with ".img" extension)
    substep : int
        every substep-th line will be included (4 in paper)
    lowfrewPercent :  float
        percent of low frequencies to add into model (0.04 in paper)

    Returns
    ------------
    imgarr: numpy.core.memmap.memmap
    An numpy image object representing a list of subsampled human-
    interpretable images.

    subsampled_img_K: numpy.core.memmap.memmap
    An numpy image object representing a list of subsampled K-space images.
    """
    #Load image
    img = nib.load(analyze_img_path)
    hdr = img.get_header()
    data = img.get_data()

    imgarr = np.ones_like(data, dtype='complex')
    subsampled_img_K = np.ones_like(data, dtype='complex')

    np.set_printoptions(threshold='nan')

    #iterate over each slice
    print(range(data.shape[2]))
    for slice in range(data.shape[2]):
        data_slice = np.squeeze(data[:,:,slice])

        # 2-dimensional fast Fourier transform
        t = np.fft.fft2(data_slice)

        # shifts 0 frequency to center
        tshift = np.fft.fftshift(t)

        # initialize a subsampled array with complex numbers
        subshift = np.ones_like(tshift)

        #Subsampler,
        #accounts for the double-counted lines
        lowfreqModifiedPercent = 1.0/float(substep)*lowfreqPercent+lowfreqPercent

        start = len(tshift)/2-int(lowfreqModifiedPercent*float(len(tshift)))
        end = len(tshift)/2+int(lowfreqModifiedPercent*float(len(tshift)))

        for i in range(0, start):
            if i % substep == 0:
                subshift[i] = tshift[i]
        for i in range (start, end):
            subshift[i] = tshift[i]
        for i in range (end, len(tshift)):
            if i % substep == 0:
                subshift[i] = tshift[i]

        print("Loaded slice: {} of image with path: {}".format(slice, analyze_img_path))
        reconsubshift = np.fft.ifft2(np.fft.ifftshift(subshift))
        imgarr[:,:,slice,0] = reconsubshift
        subsampled_img_K[:,:,slice,0] = subshift

    return imgarr, subsampled_img_K
