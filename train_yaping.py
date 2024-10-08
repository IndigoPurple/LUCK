import argparse
import torch
from torch.utils.data import DataLoader
from torch.utils.data import Dataset
from skimage.metrics import peak_signal_noise_ratio as PSNR
from skimage.metrics import structural_similarity as SSIM

import numpy as np
import os
import tqdm
import random
import imageio

from network import baseline, abflow, crossnet

# Dataloader define
def image_read(train_c_path, train_m_path, train_rgb_path):
    """
    load image data to CPU ram, our dataset cost about 30Gb ram for training.
    if you don't have enough ram, just move this "image_read" operation to "load_data"
    it will read images from path in patch everytime.

    input: (color raw images' path list, mono raw images' path list, RGB GT images' path list)
    output: datalist
    """
    gt_list = []
    inp_list = []
    gt_m_list = []

    for i in tqdm.tqdm(range(len(train_c_path))):
        color_raw = imageio.imread(train_c_path[i])
        inp_list.append(color_raw)
        mono_raw = imageio.imread(train_m_path[i])
        gt_m_list.append(mono_raw)
        gt_rgb = imageio.imread(train_rgb_path[i])
        gt_list.append(gt_rgb)

    return inp_list, gt_m_list, gt_list, train_c_path

# def read_single_image(img_path):
#
#     return imageio.imread(img_path)

class load_data(Dataset):
    """Loads the Data."""

    def __init__(self, train_c_path, train_m_path, train_rgb_path, training=True):

        self.training = training
        self.train_c_path = train_c_path
        self.train_m_path = train_m_path
        self.train_rgb_path = train_rgb_path
        # if self.training:
        #     print('\n...... Train files loading\n')
        #     self.inp_list, self.gt_m_list, self.gt_list, self.train_c_path = image_read(train_c_path, train_m_path, train_rgb_path)
        #     print('\nTrain files loaded ......\n')
        # else:
        #     print('\n...... Test files loading\n')
        #     self.inp_list, self.gt_m_list, self.gt_list, self.train_c_path = image_read(train_c_path, train_m_path, train_rgb_path)
        #     print('\nTest files loaded ......\n')

    def __len__(self):
        return len(self.train_rgb_path)

    def __getitem__(self, idx):

        gt_rgb_image = imageio.imread(self.train_rgb_path[idx])
        gt_m_image = imageio.imread(self.train_m_path[idx])
        inp_raw_image = imageio.imread(self.train_c_path[idx])

        img_num = int(self.train_c_path[idx][-23:-20])
        img_expo = int(self.train_c_path[idx][-8:-4],16)
        H, W = inp_raw_image.shape

        if img_num < 500:
            gt_expo = 12287
        else:
            gt_expo = 1023
        amp = gt_expo / img_expo

        inp_raw_image = (inp_raw_image / 255 * amp).astype(np.float32)
        gt_m_image = (gt_m_image / 255).astype(np.float32)
        gt_rgb_image = (gt_rgb_image / 255).astype(np.float32)

        if self.training:
            """
            if training, random crop and flip are employed.
            if testing, original image data will be used.
            """
            i = random.randint(0, (H - 512 - 2) // 2) * 2
            j = random.randint(0, (W - 512 - 2) // 2) * 2

            inp_raw = inp_raw_image[i:i + 512, j:j + 512]
            gt_m = gt_m_image[i:i + 512, j:j + 512]
            gt_rgb = gt_rgb_image[i:i + 512, j:j + 512, :]

            if random.randint(0, 100) > 50:
                inp_raw = np.fliplr(inp_raw).copy()
                gt_m = np.fliplr(gt_m).copy()
                gt_rgb = np.fliplr(gt_rgb).copy()

            if random.randint(0, 100) < 20:
                inp_raw = np.flipud(inp_raw).copy()
                gt_m = np.flipud(gt_m).copy()
                gt_rgb = np.flipud(gt_rgb).copy()
        else:
            inp_raw = inp_raw_image
            gt_m = gt_m_image
            gt_rgb = gt_rgb_image

        gt = torch.from_numpy((np.transpose(gt_rgb, [2, 0, 1]))).float()
        gt_mono = torch.from_numpy(gt_m).float().unsqueeze(0)
        inp = torch.from_numpy(inp_raw).float().unsqueeze(0)

        return inp, gt_mono, gt

# run test during training, more CPU ram and GPU memory needed
def run_test(model, dataloader_test, iteration, save_images_file, save_csv_file, metric_average_filename, exp_name):
    psnr1 = ['PSNR1']
    ssim1 = ['SSIM1']
    psnr2 = ['PSNR2']
    ssim2 = ['SSIM2']

    with torch.no_grad():
        model.eval()
        for image_num, img in tqdm.tqdm(enumerate(dataloader_test)):
            input_color = img[0].to(next(model.parameters()).device)
            gt_mono = img[1].to(next(model.parameters()).device)
            gt_rgb = img[2]
            rgb_pred = model(input_color, gt_mono)

            # mono_pred = (np.clip(mono_pred[0].detach().cpu().numpy().transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
            gt_mono = (np.clip(gt_mono[0].detach().cpu().numpy().transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
            rgb_pred = (np.clip(rgb_pred[0].detach().cpu().numpy().transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
            gt_rgb = (np.clip(gt_rgb[0].detach().cpu().numpy().transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)


            # psnr1_img = PSNR(mono_pred, gt_mono)
            # ssim1_img = SSIM(mono_pred, gt_mono, multichannel=True)
            psnr2_img = PSNR(rgb_pred, gt_rgb)
            ssim2_img = SSIM(rgb_pred, gt_rgb, multichannel=True)

            # save test gt and predicted images
            imageio.imwrite(os.path.join(save_images_file, '{}_{}_gt.jpg'.format(image_num, iteration)), gt_rgb)
            imageio.imwrite(os.path.join(save_images_file,'{}_{}_psnr_{:.4f}_ssim_{:.4f}.jpg'.format(image_num, iteration, psnr2_img,ssim2_img)), rgb_pred)

            # imageio.imwrite(os.path.join(save_images_file, '{}_{}_gt_mono.jpg'.format(image_num, iteration)), gt_mono)
            # imageio.imwrite(os.path.join(save_images_file,'{}_{}_psnr_{:.4f}_ssim_{:.4f}_mono.jpg'.format(image_num, iteration, psnr1_img,ssim1_img)), mono_pred)

            # psnr1.append(psnr1_img)
            # ssim1.append(ssim1_img)
            psnr2.append(psnr2_img)
            ssim2.append(ssim2_img)

    np.savetxt(os.path.join(save_csv_file, '%s_Metrics_iter_{}.csv'.format(exp_name, iteration)),
               [p for p in zip(psnr2, ssim2)], delimiter=',', fmt='%s')

    # psnr1_avg = sum(psnr1[1:]) / len(psnr1[1:])
    # ssim1_avg = sum(ssim1[1:]) / len(ssim1[1:])
    psnr2_avg = sum(psnr2[1:]) / len(psnr2[1:])
    ssim2_avg = sum(ssim2[1:]) / len(ssim2[1:])

    # save test metrics
    f = open(metric_average_filename, 'a')
    f.write('-- psnr2_avg: {}, ssim2_avg: {} iter: {}\n'.format(psnr2_avg, ssim2_avg, iteration))
    print('average metric saved.')
    f.close()

    return

if __name__ == '__main__':

    # Arguments
    parser = argparse.ArgumentParser()
    ## Dataset and loader
    # parser.add_argument('--dataset_root', type=str, default='./data')
    # parser.add_argument('--dataset', type=str, default='PUNet')
    # parser.add_argument('--patch_size', type=int, default=1000)
    # parser.add_argument('--resolutions', type=str_list, default=['10000_poisson', '30000_poisson', '50000_poisson'])
    # parser.add_argument('--noise_min', type=float, default=0.005)
    # parser.add_argument('--noise_max', type=float, default=0.020)
    parser.add_argument('--batch_size', type=int, default=24)
    parser.add_argument('--num_workers', type=int, default=4)
    # parser.add_argument('--aug_rotate', type=eval, default=True, choices=[True, False])
    ## Model architecture
    parser.add_argument('--net', type=str, default='baseline')
    ## Optimizer and scheduler
    # parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--weight_decay', type=float, default=0)
    # parser.add_argument('--max_grad_norm', type=float, default=float("inf"))
    ## Training
    parser.add_argument('--gpu_id', type=str, default='0')
    parser.add_argument('--iterations', type=int, default=500000)
    parser.add_argument('--exp_name', type=str, default='baseline')
    args = parser.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"]=args.gpu_id

    opt={'base_lr':1e-4}
    # opt['batch_size'] = 1 # default = 24
    # opt['iterations'] = 500000

    metric_average_file = 'result/%s_metric_average.txt' % args.exp_name
    # These are folders
    save_weights_file = 'result/weights'
    save_images_file = 'result/images/%s' % args.exp_name
    save_csv_file = 'result/csv_files'

    if not os.path.exists(save_weights_file):
        os.makedirs(save_weights_file)
    if not os.path.exists(save_images_file):
        os.makedirs(save_images_file)
    if not os.path.exists(save_csv_file):
        os.makedirs(save_csv_file)

    # load random image paths
    train_c_path = np.load('./random_path_list/train/train_c_path.npy')
    train_m_path = np.load('./random_path_list/train/train_m_path.npy')
    train_rgb_path = np.load('./random_path_list/train/train_rgb_path.npy')
    test_c_path = np.load('./random_path_list/test/test_c_path.npy')
    test_m_path = np.load('./random_path_list/test/test_m_path.npy')
    test_rgb_path = np.load('./random_path_list/test/test_rgb_path.npy')

    print('train data: %d pairs'%len(train_c_path))
    print('test data: %d pairs'%len(test_c_path))
    dataloader_train = DataLoader(load_data(train_c_path,train_m_path,train_rgb_path,training=True), batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, pin_memory=True,prefetch_factor=8) # num_workers=4
    # run test during training, more time and CPU memory needed
    dataloader_test = DataLoader(load_data(test_c_path,test_m_path,test_rgb_path,training=False), batch_size=1, shuffle=False, num_workers=0, pin_memory=True)


    device = torch.device("cuda")

    if args.net == 'baseline':
        model = baseline()
    elif args.net == 'abflow':
        model = abflow()
    elif args.net == 'crossnet':
        model = crossnet()
    print(model)
    # checkpoint = torch.load(save_weights_file + '/weights_120000.pth')
    checkpoint = torch.load(save_weights_file + '/MCR_weights_280000.pth')
    model.load_state_dict(checkpoint['model'],strict=False)
    print('\nTrainable parameters : {}\n'.format(sum(p.numel() for p in model.parameters() if p.requires_grad)))
    print('\nTotal parameters : {}\n'.format(sum(p.numel() for p in model.parameters())))
    model = model.to(device)
    print('Device on cuda: {}'.format(next(model.parameters()).is_cuda))

    iter_num = 0
    l1_loss = torch.nn.L1Loss()

    optimizer = torch.optim.Adam(model.parameters(), lr=opt['base_lr'])
    optimizer.zero_grad()
    loss_list = ['loss']
    metrics = ['PSNR_rgb, SSIM_rgb']
    iter_list = ['Iteration']
    iter_LR = ['Iter_LR']

    while iter_num < args.iterations:
        for _, img in tqdm.tqdm(enumerate(dataloader_train)):
            color_raw = img[0].to(device)
            mono_raw = img[1].to(device)
            rgb = img[2].to(device)

            model.train()
            rgb_pred = model(color_raw, mono_raw)
            iter_num += 1

            loss = l1_loss(rgb_pred, rgb)

            loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            if iter_num >args.iterations:
                break

            # print and save info every 100 iter
            if iter_num % 100 == 0:
                # psnr_mono = PSNR(mono_raw.detach().cpu().numpy().transpose(0, 2, 3, 1),
                #             np.clip(mono_pred.detach().cpu().numpy().transpose(0, 2, 3, 1), 0, 1))
                psnr_rgb = PSNR(rgb.detach().cpu().numpy().transpose(0, 2, 3, 1),
                            np.clip(rgb_pred.detach().cpu().numpy().transpose(0, 2, 3, 1), 0, 1))
                # print(mono_raw.shape, mono_pred.shape)
                # raw = mono_raw.detach().cpu().numpy()[:,:,:,0].transpose(1,2,0) * 255
                # pred = np.clip(mono_pred.detach().cpu().numpy()[:,:,:,0].transpose(1,2,0) * 255, 0, 255)
                # print(raw.shape, pred.shape)
                # ssim_mono = SSIM(mono_raw.detach().cpu().numpy().transpose(0, 2, 3, 1)*255,
                #             np.clip(mono_pred.detach().cpu().numpy().transpose(0, 2, 3, 1)*255, 0, 255), multichannel=True)
                # ssim_rgb = SSIM(rgb.detach().cpu().numpy().transpose(0, 2, 3, 1)*255,
                #             np.clip(rgb_pred.detach().cpu().numpy().transpose(0, 2, 3, 1)*255, 0, 255), multichannel=True)
                # print(mono_raw.detach().cpu().numpy()[0,:,:,:].transpose(1,2,0).shape)
                # ssim_mono = SSIM(mono_raw.detach().cpu().numpy()[0,:,:,:].transpose(1,2,0) * 255,
                #                  np.clip(mono_pred.detach().cpu().numpy()[0,:,:,:].transpose(1,2,0) * 255, 0, 255),
                #                  multichannel=True)
                ssim_rgb = SSIM(rgb.detach().cpu().numpy()[0,:,:,:].transpose(1,2,0) * 255,
                                np.clip(rgb_pred.detach().cpu().numpy()[0,:,:,:].transpose(1,2,0) * 255, 0, 255),
                                multichannel=True)

                print('\niter_num:%.0f, loss_rgb:%.4f, PSNR_rgb:%.4f, SSIM_rgb:%.4f' % (
                iter_num, np.mean(loss.detach().cpu().numpy()), np.mean(psnr_rgb), np.mean(ssim_rgb)))

                loss_list.append('{:.5f}'.format(loss.item()))
                metrics.append('{:.5f},{:.5f}'.format(np.mean(psnr_rgb), np.mean(ssim_rgb)))
                iter_list.append(iter_num)
                iter_LR.append(optimizer.param_groups[0]['lr'])
                np.savetxt(os.path.join(save_csv_file, '%s_train_curve.csv'%args.exp_name), [p for p in zip(iter_list, iter_LR, loss_list, metrics)], delimiter=',', fmt='%s')

            # save checkpoint every 20000 times, make adjustments accordingly
            if iter_num % 100000 == 0:
                torch.save({'model': model.state_dict()}, os.path.join(save_weights_file, '{}_weights_{}.pth'.format(args.exp_name, iter_num)))
                print('model saved......')
            # run test during training, more CPU ram and GPU memory needed.
            if iter_num % 100000 == 0:
                run_test(model, dataloader_test, iter_num, save_images_file, save_csv_file, metric_average_file, exp_name = args.exp_name)