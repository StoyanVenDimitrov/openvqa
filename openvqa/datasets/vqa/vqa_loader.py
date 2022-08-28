# --------------------------------------------------------
# OpenVQA
# Written by Yuhao Cui https://github.com/cuiyuhao1996
# --------------------------------------------------------
import torch
import numpy as np
import glob, json, re, en_core_web_lg
from openvqa.core.base_dataset import BaseDataSet
from openvqa.utils.ans_punct import prep_ans
from irl_dcb import utils

class DataSet(BaseDataSet):
    def __init__(self, __C):
        super(DataSet, self).__init__()
        self.__C = __C

        # --------------------------
        # ---- Raw data loading ----
        # --------------------------

        # Loading all image paths
        frcn_feat_path_list = \
            glob.glob(__C.FEATS_PATH[__C.DATASET]['train'] + '/*.npz') + \
            glob.glob(__C.FEATS_PATH[__C.DATASET]['val'] + '/*.npz') + \
            glob.glob(__C.FEATS_PATH[__C.DATASET]['test'] + '/*.npz')
        lr_frcn_feat_path_list = \
            glob.glob('./data/vqa/dcb/train2014/LR/' + '/*.pth.tar') + \
            glob.glob('./data/vqa/dcb/val2014/LR/' + '/*.pth.tar') + \
            glob.glob('./data/vqa/dcb/test2015/LR/' + '/*.pth.tar')
        hr_frcn_feat_path_list = \
            glob.glob('./data/vqa/dcb/train2014/HR/' + '/*.pth.tar') + \
            glob.glob('./data/vqa/dcb/val2014/HR/' + '/*.pth.tar') + \
            glob.glob('./data/vqa/dcb/test2015/HR/' + '/*.pth.tar')
        # Loading question word list
        stat_ques_list = \
            json.load(open(__C.RAW_PATH[__C.DATASET]['train'], 'r'))['questions'] + \
            json.load(open(__C.RAW_PATH[__C.DATASET]['val'], 'r'))['questions'] + \
            json.load(open(__C.RAW_PATH[__C.DATASET]['test'], 'r'))['questions'] + \
            json.load(open(__C.RAW_PATH[__C.DATASET]['vg'], 'r'))['questions']

        # Loading answer word list
        # stat_ans_list = \
        #     json.load(open(__C.RAW_PATH[__C.DATASET]['train-anno'], 'r'))['annotations'] + \
        #     json.load(open(__C.RAW_PATH[__C.DATASET]['val-anno'], 'r'))['annotations']

        # Loading question and answer list
        self.ques_list = []
        self.ans_list = []

        split_list = __C.SPLIT[__C.RUN_MODE].split('+')
        for split in split_list:
            self.ques_list += json.load(open(__C.RAW_PATH[__C.DATASET][split], 'r'))['questions']
            if __C.RUN_MODE in ['train']:
                self.ans_list += json.load(open(__C.RAW_PATH[__C.DATASET][split + '-anno'], 'r'))['annotations']

        # Define run data size
        if __C.RUN_MODE in ['train']:
            self.data_size = self.ans_list.__len__()
        else:
            self.data_size = self.ques_list.__len__()

        print(' ========== Dataset size:', self.data_size)


        # ------------------------
        # ---- Data statistic ----
        # ------------------------

        # {image id} -> {image feature absolutely path}
        self.iid_to_frcn_feat_path = self.img_feat_path_load(frcn_feat_path_list)
        self.lr_iid_to_frcn_feat_path = self.img_feat_path_load(lr_frcn_feat_path_list)
        self.hr_iid_to_frcn_feat_path = self.img_feat_path_load(hr_frcn_feat_path_list)

        # {question id} -> {question}
        self.qid_to_ques = self.ques_load(self.ques_list)

        # Tokenize
        self.token_to_ix, self.pretrained_emb = self.tokenize(stat_ques_list, __C.USE_GLOVE)
        self.token_size = self.token_to_ix.__len__()
        print(' ========== Question token vocab size:', self.token_size)

        # Answers statistic
        self.ans_to_ix, self.ix_to_ans = self.ans_stat('openvqa/datasets/vqa/answer_dict.json')
        # self.ans_to_ix, self.ix_to_ans = self.ans_stat(stat_ans_list, ans_freq=8)
        self.ans_size = self.ans_to_ix.__len__()
        print(' ========== Answer token vocab size (occur more than {} times):'.format(8), self.ans_size)
        print('Finished!')
        print('')

    def __getitem__(self, idx):

        ques_ix_iter, ans_iter, iid = self.load_ques_ans(idx)

        frcn_feat_iter, grid_feat_iter, bbox_feat_iter, scanpath_feat_iter = self.load_img_feats(idx, iid)

        return \
            torch.from_numpy(frcn_feat_iter),\
            torch.from_numpy(grid_feat_iter),\
            torch.from_numpy(bbox_feat_iter),\
            torch.from_numpy(ques_ix_iter),\
            torch.from_numpy(ans_iter),\
            scanpath_feat_iter    

    def img_feat_path_load(self, path_list):
        iid_to_path = {}

        for ix, path in enumerate(path_list):
            iid = str(int(path.split('/')[-1].split('_')[-1].split('.')[0]))
            # print(iid)
            iid_to_path[iid] = path

        return iid_to_path


    def ques_load(self, ques_list):
        qid_to_ques = {}

        for ques in ques_list:
            qid = str(ques['question_id'])
            qid_to_ques[qid] = ques

        return qid_to_ques


    def tokenize(self, stat_ques_list, use_glove):
        token_to_ix = {
            'PAD': 0,
            'UNK': 1,
            'CLS': 2,
        }

        spacy_tool = None
        pretrained_emb = []
        if use_glove:
            spacy_tool = en_core_web_lg.load()
            pretrained_emb.append(spacy_tool('PAD').vector)
            pretrained_emb.append(spacy_tool('UNK').vector)
            pretrained_emb.append(spacy_tool('CLS').vector)

        # for ques in stat_ques_list:
        #     words = re.sub(
        #         r"([.,'!?\"()*#:;])",
        #         '',
        #         ques['question'].lower()
        #     ).replace('-', ' ').replace('/', ' ').split()

        #     for word in words:
        #         if word not in token_to_ix:
        #             token_to_ix[word] = len(token_to_ix)
        #             if use_glove:
        #                 pretrained_emb.append(spacy_tool(word).vector)

        pretrained_emb = np.array(pretrained_emb)

        return token_to_ix, pretrained_emb


    # def ans_stat(self, stat_ans_list, ans_freq):
    #     ans_to_ix = {}
    #     ix_to_ans = {}
    #     ans_freq_dict = {}
    #
    #     for ans in stat_ans_list:
    #         ans_proc = prep_ans(ans['multiple_choice_answer'])
    #         if ans_proc not in ans_freq_dict:
    #             ans_freq_dict[ans_proc] = 1
    #         else:
    #             ans_freq_dict[ans_proc] += 1
    #
    #     ans_freq_filter = ans_freq_dict.copy()
    #     for ans in ans_freq_dict:
    #         if ans_freq_dict[ans] <= ans_freq:
    #             ans_freq_filter.pop(ans)
    #
    #     for ans in ans_freq_filter:
    #         ix_to_ans[ans_to_ix.__len__()] = ans
    #         ans_to_ix[ans] = ans_to_ix.__len__()
    #
    #     return ans_to_ix, ix_to_ans

    def ans_stat(self, json_file):
        ans_to_ix, ix_to_ans = json.load(open(json_file, 'r'))

        return ans_to_ix, ix_to_ans



    # ----------------------------------------------
    # ---- Real-Time Processing Implementations ----
    # ----------------------------------------------

    def load_ques_ans(self, idx):
        if self.__C.RUN_MODE in ['train']:
            ans = self.ans_list[idx]
            ques = self.qid_to_ques[str(ans['question_id'])]
            iid = str(ans['image_id'])

            # Process question
            ques_ix_iter = self.proc_ques(ques, self.token_to_ix, max_token=14)

            # Process answer
            ans_iter = self.proc_ans(ans, self.ans_to_ix)

            return ques_ix_iter, ans_iter, iid

        else:
            ques = self.ques_list[idx]
            iid = str(ques['image_id'])

            ques_ix_iter = self.proc_ques(ques, self.token_to_ix, max_token=14)

            return ques_ix_iter, np.zeros(1), iid


    def load_img_feats(self, idx, iid):
        frcn_feat = np.load(self.iid_to_frcn_feat_path[iid])
        lr_frcn_feat = torch.load(self.lr_iid_to_frcn_feat_path[iid])
        hr_frcn_feat = torch.load(self.hr_iid_to_frcn_feat_path[iid])

        frcn_feat_x = frcn_feat['x'].transpose((1, 0))
        frcn_feat_iter = self.proc_img_feat(frcn_feat_x, img_feat_pad_size=self.__C.FEAT_SIZE['vqa']['FRCN_FEAT_SIZE'][0])

        bbox_feat_iter = self.proc_img_feat(
            self.proc_bbox_feat(
                frcn_feat['bbox'],
                (frcn_feat['image_h'], frcn_feat['image_w'])
            ),
            img_feat_pad_size=self.__C.FEAT_SIZE['vqa']['BBOX_FEAT_SIZE'][0]
        )
        grid_feat_iter = np.zeros(1)
        scanpath_feat_iter = self.init_scanpath_feat(hr_frcn_feat, lr_frcn_feat)
        return frcn_feat_iter, grid_feat_iter, bbox_feat_iter, scanpath_feat_iter



    # ------------------------------------
    # ---- Real-Time Processing Utils ----
    # ------------------------------------

    def proc_img_feat(self, img_feat, img_feat_pad_size):
        if img_feat.shape[0] > img_feat_pad_size:
            img_feat = img_feat[:img_feat_pad_size]

        img_feat = np.pad(
            img_feat,
            ((0, img_feat_pad_size - img_feat.shape[0]), (0, 0)),
            mode='constant',
            constant_values=0
        )

        return img_feat


    def proc_bbox_feat(self, bbox, img_shape):
        if self.__C.BBOX_NORMALIZE:
            bbox_nm = np.zeros((bbox.shape[0], 4), dtype=np.float32)

            bbox_nm[:, 0] = bbox[:, 0] / float(img_shape[1])
            bbox_nm[:, 1] = bbox[:, 1] / float(img_shape[0])
            bbox_nm[:, 2] = bbox[:, 2] / float(img_shape[1])
            bbox_nm[:, 3] = bbox[:, 3] / float(img_shape[0])
            return bbox_nm
        # bbox_feat[:, 4] = (bbox[:, 2] - bbox[:, 0]) * (bbox[:, 3] - bbox[:, 1]) / float(img_shape[0] * img_shape[1])

        return bbox


    def proc_ques(self, ques, token_to_ix, max_token):
        ques_ix = np.zeros(max_token, np.int64)

        words = re.sub(
            r"([.,'!?\"()*#:;])",
            '',
            ques['question'].lower()
        ).replace('-', ' ').replace('/', ' ').split()

        for ix, word in enumerate(words):
            if word in token_to_ix:
                ques_ix[ix] = token_to_ix[word]
            else:
                ques_ix[ix] = token_to_ix['UNK']

            if ix + 1 == max_token:
                break

        return ques_ix


    def get_score(self, occur):
        if occur == 0:
            return .0
        elif occur == 1:
            return .3
        elif occur == 2:
            return .6
        elif occur == 3:
            return .9
        else:
            return 1.


    def proc_ans(self, ans, ans_to_ix):
        ans_score = np.zeros(ans_to_ix.__len__(), np.float32)
        ans_prob_dict = {}

        for ans_ in ans['answers']:
            ans_proc = prep_ans(ans_['answer'])
            if ans_proc not in ans_prob_dict:
                ans_prob_dict[ans_proc] = 1
            else:
                ans_prob_dict[ans_proc] += 1

        if self.__C.LOSS_FUNC in ['kld']:
            for ans_ in ans_prob_dict:
                if ans_ in ans_to_ix:
                    ans_score[ans_to_ix[ans_]] = ans_prob_dict[ans_] / 10.
        else:
            for ans_ in ans_prob_dict:
                if ans_ in ans_to_ix:
                    ans_score[ans_to_ix[ans_]] = self.get_score(ans_prob_dict[ans_])

        return ans_score

    def init_scanpath_feat(self, hr, lr):
        """ a reduced version of LHF_IRL(Dataset) __getitem__()"""
        # update state with initial fixation
        px, py = 0.5, 0.5
        px, py = px * lr.size(-1), py * lr.size(-2)
        mask = utils.foveal2mask(px, py, 2, hr.size(-2),
                                 hr.size(-1))
        mask = torch.from_numpy(mask)
        mask = mask.unsqueeze(0).repeat(hr.size(0), 1, 1)
        lr = (1 - mask) * lr + mask * hr

        # history fixation map
        history_map = torch.zeros((hr.size(-2), hr.size(-1)))
        history_map = (1 - mask[0]) * history_map + mask[0] * 1

        # action mask
        action_mask = torch.zeros((10, 10),
                                  dtype=torch.uint8)
        px, py = 0.5, 0.5
        px, py = int(px * 10), int(py * 10)
        action_mask[py - 1:py + 1 + 1, px -
                    1:px + 1 + 1] = 1
        return {
            'lr_feats': lr,
            'hr_feats': hr,
            'history_map': history_map,
            'init_fix': torch.FloatTensor((0.5, 0.5)),
            'action_mask': action_mask,
            'img_name': torch.empty(1),
            'cat_name': torch.empty(1),
            'task_id': torch.empty(1),
            'label_coding': torch.empty(1)
        }
