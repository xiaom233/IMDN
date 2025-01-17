import os.path
import logging
from collections import OrderedDict
from copy import deepcopy
import torch
from utils import utils_logger
from utils import utils_image as util
from models.rfdnfinalB5_arch import RFDNFINALB5
from torch.nn.parallel import DataParallel, DistributedDataParallel

def main():

    utils_logger.logger_info('NTIRE2022-EfficientSR', log_path='NTIRE2022-EfficientSR.log')
    logger = logging.getLogger('NTIRE2022-EfficientSR')

    # --------------------------------
    # basic settings
    # --------------------------------
    # testsets = 'DIV2K'
    testsets = os.path.join(os.getcwd(), 'data')
    testset_L = 'DIV2K_test_LR'

    torch.cuda.current_device()
    torch.cuda.empty_cache()
    torch.backends.cudnn.benchmark = False
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # --------------------------------
    # load model
    # --------------------------------
    model_path = os.path.join('model_zoo', 'final.pth')
    model = RFDNFINALB5(num_in_ch=3, num_feat=48, num_block=5, num_out_ch=3, upscale=4,
                 conv='BSConvU', upsampler='pixelshuffledirect')
    if isinstance(model, (DataParallel, DistributedDataParallel)):
        model = model.module
    load_net = torch.load(model_path, map_location=lambda storage, loc: storage)
    param_key = 'params' #RCAN
    if param_key is not None:
        if param_key not in load_net and 'params' in load_net:
            param_key = 'params'
            logger.info('Loading: params_ema does not exist, use params.')
        load_net = load_net[param_key]
    model.load_state_dict(load_net, strict=True)
    # remove unnecessary 'module.'
    for k, v in deepcopy(load_net).items():
        if k.startswith('module.'):
            load_net[k[7:]] = v
            load_net.pop(k)
    model.load_state_dict(load_net, strict=True)
    model.eval()
    for k, v in model.named_parameters():
        v.requires_grad = False
    model = model.to(device)
    # number of parameters
    number_parameters = sum(map(lambda x: x.numel(), model.parameters()))
    logger.info('Params number: {}'.format(number_parameters))

    # --------------------------------
    # read image
    # --------------------------------
    L_folder = os.path.join(testsets, testset_L)
    E_folder = os.path.join(testsets, testset_L+'_results')
    util.mkdir(E_folder)

    # record PSNR, runtime
    test_results = OrderedDict()
    test_results['runtime'] = []

    logger.info(L_folder)
    logger.info(E_folder)
    idx = 0

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)

    for img in util.get_image_paths(L_folder):

        # --------------------------------
        # (1) img_L
        # --------------------------------
        idx += 1
        img_name, ext = os.path.splitext(os.path.basename(img))
        logger.info('{:->4d}--> {:>10s}'.format(idx, img_name+ext))

        img_L = util.imread_uint(img, n_channels=3)
        img_L = util.uint2tensor4(img_L)
        img_L = img_L.to(device)

        start.record()
        img_E = model(img_L)
        end.record()
        torch.cuda.synchronize()
        test_results['runtime'].append(start.elapsed_time(end))  # milliseconds


#        torch.cuda.synchronize()
#        start = time.time()
#        img_E = model(img_L)
#        torch.cuda.synchronize()
#        end = time.time()
#        test_results['runtime'].append(end-start)  # seconds

        # --------------------------------
        # (2) img_E
        # --------------------------------
        img_E = util.tensor2uint(img_E)

        util.imsave(img_E, os.path.join(E_folder, img_name[:4]+ext))
    ave_runtime = sum(test_results['runtime']) / len(test_results['runtime']) / 1000.0
    logger.info('------> Average runtime of ({}) is : {:.6f} seconds'.format(L_folder, ave_runtime))

if __name__ == '__main__':

    main()
