import copy
import random

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm

from cogdl import options
from cogdl.datasets import build_dataset
from cogdl.models import build_model

from . import BaseTask, register_task


@register_task("node_classification")
class NodeClassification(BaseTask):
    """Node classification task."""

    @staticmethod
    def add_args(parser):
        """Add task-specific arguments to the parser."""
        # fmt: off
        # parser.add_argument("--num-features", type=int)
        # fmt: on

    def __init__(self, args):
        super(NodeClassification, self).__init__(args)

        dataset = build_dataset(args)
        self.data = dataset.data
        self.data.apply(lambda x: x.cuda())
        args.num_features = dataset.num_features
        args.num_classes = dataset.num_classes
        model = build_model(args)
        self.model = model.cuda()
        self.patience = args.patience
        self.max_epoch = args.max_epoch

        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=args.lr, weight_decay=args.weight_decay
        )

    def train(self):
        epoch_iter = tqdm(range(self.max_epoch))
        patience = 0
        best_score = 0
        best_loss = np.inf
        max_score = 0
        min_loss = np.inf
        for epoch in epoch_iter:
            self._train_step()
            train_acc, _ = self._test_step(split="train")
            val_acc, val_loss = self._test_step(split="val")
            epoch_iter.set_description(
                f"Epoch: {epoch:03d}, Train: {train_acc:.4f}, Val: {val_acc:.4f}"
            )
            if val_loss <= min_loss or val_acc >= max_score:
                if val_loss <= best_loss:  # and val_acc >= best_score:
                    best_loss = val_loss
                    best_score = val_acc
                    best_model = copy.deepcopy(self.model)
                min_loss = np.min((min_loss, val_loss))
                max_score = np.max((max_score, val_acc))
                patience = 0
            else:
                patience += 1
                if patience == self.patience:
                    self.model = best_model
                    epoch_iter.close()
                    break
        test_acc, _ = self._test_step(split="test")
        print(f"Test accuracy = {test_acc}")
        return dict(
            Acc=test_acc
        )

    def _train_step(self):
        self.model.train()
        self.optimizer.zero_grad()
        F.nll_loss(
            self.model(self.data.x, self.data.edge_index)[self.data.train_mask],
            self.data.y[self.data.train_mask],
        ).backward()
        self.optimizer.step()

    def _test_step(self, split="val"):
        self.model.eval()
        logits = self.model(self.data.x, self.data.edge_index)
        _, mask = list(self.data(f"{split}_mask"))[0]
        loss = F.nll_loss(
            logits[mask],
            self.data.y[mask],
        )
        
        pred = logits[mask].max(1)[1]
        acc = pred.eq(self.data.y[mask]).sum().item() / mask.sum().item()
        return acc, loss
