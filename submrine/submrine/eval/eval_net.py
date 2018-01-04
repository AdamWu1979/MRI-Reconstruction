import sys
import os
import argparse
import keras
import numpy as np
import json

from ..utils import subsample, correct_output, load_image_data, get_image_file_paths, normalize, create_output_dir
from matplotlib import pyplot as plt
from skimage.measure import compare_ssim as ssim

# Data loading
ANALYZE_DATA_EXTENSION_IMG = ".img"

# Network evaluation
LOSS_TYPE_MSE = "mse"
LOSS_TYPE_SSIM = "ssim"

# Loss computation
NUM_EVALUATION_SLICES = 35

# Result writing
SFX_LOSS_EVALUATION = "losses"
SFX_DIFF_PLOTS = "diffs"

FNAME_LOSS_EVALUATION = "results.txt"

def load_image(raw_img_path, substep, low_freq_percent):
    original_img = load_image_data(analyze_img_path=raw_img_path)
    subsampled_img, subsampled_K = subsample(analyze_img_data=original_img, 
                                             substep=substep, 
                                             low_freq_percent=low_freq_percent)

    original_img = np.moveaxis(original_img, -1, 0)
    subsampled_img = np.moveaxis(subsampled_img, -1, 0)
    subsampled_K = np.moveaxis(subsampled_K, -1, 0)

    return subsampled_img, subsampled_K, original_img

def load_net(net_path):
    return keras.models.load_model(net_path)

def reconstruct_slice(fnet, subsampled_slice, subsampled_slice_k, substep, low_freq_percent):
    # Reshape input to shape (1, SLICE_WIDTH, SLICE_HEIGHT, 1)
    fnet_input = np.expand_dims(subsampled_slice, 0)
    fnet_input = np.expand_dims(fnet_input, -1)

    fnet_output = fnet.predict(fnet_input)
    fnet_output = normalize(fnet_output)
    fnet_output = np.squeeze(fnet_output)

    correction_subsampled_input = np.squeeze(subsampled_slice_k)
    corrected_output = correct_output(subsampled_img_K=correction_subsampled_input,
                                      network_output=fnet_output,
                                      substep=substep,
                                      low_freq_percent=low_freq_percent)

    return corrected_output


def eval_diff_plot(net_path, img_path, substep, low_freq_percent, results_dir, exp_name):
    [
        test_subsampled, 
        test_subsampled_K, 
        test_original
    ] = load_image(raw_img_path=img_path, 
                   substep=substep, 
                   low_freq_percent=low_freq_percent)

    fnet = load_net(net_path=net_path)

    output_dir_path = create_output_dir(base_path=results_dir, suffix=SFX_DIFF_PLOTS, exp_name=exp_name)

    for slice_idx in range(len(test_subsampled)):
        reconstructed_slice = reconstruct_slice(fnet=fnet,
                                                subsampled_slice=test_subsampled[slice_idx],
                                                subsampled_slice_k=test_subsampled_K[slice_idx],
                                                substep=substep,
                                                low_freq_percent=low_freq_percent)

        plt.subplot(121), plt.imshow(test_original[slice_idx], cmap='gray')
        plt.title('Original Slice'), plt.xticks([]), plt.yticks([])
        plt.subplot(122), plt.imshow(np.squeeze(reconstructed_slice), cmap='gray')
        plt.title('Reconstructed Slice'), plt.xticks([]), plt.yticks([])
        plt.subplot(123), plt.imshow(np.squeeze(test_subsampled[slice_idx]), cmap='gray')
        plt.title('Subsampled Slice'), plt.xticks([]), plt.yticks([])

        plot_path = os.path.join(output_dir_path, "{}.png".format(slice_idx))
        plt.savefig(plot_path, bbox_inches='tight')

        print("Wrote diff plot for slice {idx} to {pp}".format(idx=slice_idx, pp=plot_path))

def compute_loss(output, original, loss_type):
    output = np.array(output, dtype=np.float64) / 255.0
    original = np.array(original, dtype=np.float64) / 255.0
    if loss_type == LOSS_TYPE_MSE:
        return np.mean((output - original)**2)
    elif loss_type == LOSS_TYPE_SSIM:
        return ssim(output, original)
    else:
        raise Exception("Attempted to compute an invalid loss!")


def eval_loss(net_path, data_path, size, loss_type, substep, low_freq_percent, results_dir, exp_name):
    fnet = load_net(net_path)
    img_paths = get_image_file_paths(data_path)
    losses = []
    aliased_losses = []
    for img_path in img_paths:
        [
            test_subsampled, 
            test_subsampled_k, 
            test_original
        ] = load_image(raw_img_path=img_path, 
                       substep=substep, 
                       low_freq_percent=low_freq_percent)
        num_slices = len(test_subsampled)
        if num_slices > NUM_EVALUATION_SLICES:
            slice_idxs_low = (num_slices - NUM_EVALUATION_SLICES) // 2
            slice_idxs_high = slice_idxs_low + NUM_EVALUATION_SLICES
            slice_idxs = range(slice_idxs_low, slice_idxs_high)
        else:
            slice_idxs = range(num_slices)

        for slice_idx in slice_idxs:
            reconstructed_slice = reconstruct_slice(fnet=fnet,
                                                    subsampled_slice=test_subsampled[slice_idx],
                                                    subsampled_slice_k=test_subsampled_k[slice_idx],
                                                    substep=substep,
                                                    low_freq_percent=low_freq_percent)

            loss = compute_loss(
                output=reconstructed_slice,
                original=test_original[slice_idx],
                loss_type=loss_type)
            losses.append(loss)
            aliased_loss = compute_loss(
                output=test_subsampled[slice_idx],
                original=test_original[slice_idx],
                loss_type=loss_type)
            aliased_losses.append(aliased_loss)
            print("Evaluated {} images".format(len(losses)))
            if len(losses) >= size:
                break

        else:
            continue

        break

    reconstructed_mean = np.mean(losses)
    reconstructed_std = np.std(losses)

    aliased_mean = np.mean(aliased_losses)
    aliased_std = np.std(aliased_losses)

    print("Aliased MEAN: {}\nAliased STD: {}\nReconstructed MEAN: {}\nReconstructed STD: {}".format(
        aliased_mean, aliased_std, reconstructed_mean, reconstructed_std))

    write_loss_results(results_dir=results_dir,
                       exp_name=exp_name,
                       aliased_mean=aliased_mean,
                       aliased_std=aliased_std,
                       reconstructed_mean=reconstructed_mean,
                       reconstructed_std=reconstructed_std)

    return losses

def write_loss_results(results_dir, exp_name, aliased_mean, alised_std, reconstructed_mean, reconstructed_std):
    output_dir_path = create_output_dir(base_path=results_dir, suffix=SFX_LOSS_EVALUATION, exp_name=exp_name)
    results_path = os.path.join(output_dir_path, FNAME_LOSS_EVALUATION)

    results_dict = {
        "aliased_mean" : aliased_mean,
        "aliased_std" : aliased_std,
        "reconstructed_mean" : reconstructed_mean,
        "reconstructed_std" : reconstructed_std
    }

    with open(results_path, "w") as results_file:
        json.dump(results_dict, results_file)

    print("Wrote results to {}".format(results_path))

def main():
    parser = argparse.ArgumentParser(
        description='Train FNet on MRI image data')
    parser.add_argument(
        '-i',
        '--img_path',
        type=str,
        help="The path to a full-resolution MR image to subsample, reconstruct, and diff-plot")
    parser.add_argument(
        '-n', '--net_path', type=str, help="The path to a trained FNet")
    parser.add_argument(
        '-d',
        '--data_path',
        type=str,
        help=
        "The path to a test set of full-resolution MR images to evaluate for loss computation"
    )
    parser.add_argument(
        '-s',
        '--substep',
        type=int,
        default=4,
        help="The substep used for subsampling (4 in the paper)")
    parser.add_argument(
        '-f',
        '--lf_percent',
        type=float,
        default=.04,
        help=
        "The percentage of low frequency data to retain when subsampling training images"
    )
    parser.add_argument(
        '-t',
        '--test_size',
        type=str,
        default=400,
        help="The size of the test set (used if --data_path is specified)")
    parser.add_argument(
        '-l',
        '--loss_type',
        type=str,
        default='mse',
        help="The type of evaluation loss. One of: 'mse', 'ssim'")
    parser.add_argument(
        '-r',
        '--results_dir',
        type=str,
        default='/tmp',
        help="The base directory to which to write evaluation results")
    parser.add_argument(
        '-e',
        '--experiment_name',
        type=str,
        help="The name of the experiment to use when writing evaluation results")

    args = parser.parse_args()

    if not args.substep:
        raise Exception("--substep must be specified!")
    elif not args.net_path:
        raise Exception("--net_path must be specified!")

    if args.img_path:
        eval_diff_plot(net_path=args.net_path,
                       img_path=args.img_path, 
                       substep=args.substep,
                       low_freq_percent=args.lf_percent,
                       results_dir=args.results_dir,
                       exp_name=args.experiment_name)
    elif args.data_path:
        if not args.test_size:
            raise Exception("--test_size must be specified!")

        eval_loss(net_path=args.net_path,
                  data_path=args.data_path,
                  size=int(args.test_size),
                  loss_type=args.loss_type,
                  substep=args.substep,
                  low_freq_percent=args.lf_percent,
                  results_dir=args.results_dir,
                  exp_name=args.experiment_name)
    else:
        raise Exception(
            "Either '--img_path' or '--data_path' must be specified!")


if __name__ == "__main__":
    main()
