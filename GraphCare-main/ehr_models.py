from pyhealth.datasets import MIMIC3Dataset, MIMIC4Dataset

from pyhealth.datasets import get_dataloader

import pickle
from pyhealth.trainer import Trainer
import torch
from pyhealth.models import Transformer, RETAIN, SafeDrug, MICRON, CNN, RNN, GAMENet
from collections import defaultdict
import json
from itertools import chain
from typing import Optional, Tuple, Union, List

import numpy as np
import torch

from pyhealth.datasets import SampleDataset


def split_by_patient(
        dataset: SampleDataset,
        ratios: Union[Tuple[float, float, float], List[float]],
        train_ratio=1.0,
        seed: Optional[int] = None,
):
    if seed is not None:
        np.random.seed(seed)
    assert sum(ratios) == 1.0, "ratios must sum to 1.0"
    patient_indx = list(dataset.patient_to_index.keys())
    num_patients = len(patient_indx)
    np.random.shuffle(patient_indx)
    train_patient_indx = patient_indx[: int(num_patients * ratios[0])]
    np.random.seed(seed)
    np.random.shuffle(train_patient_indx)
    train_patient_indx = train_patient_indx[: int(len(train_patient_indx) * train_ratio)]
    val_patient_indx = patient_indx[
                       int(num_patients * ratios[0]): int(
                           num_patients * (ratios[0] + ratios[1]))
                       ]
    test_patient_indx = patient_indx[int(num_patients * (ratios[0] + ratios[1])):]
    train_index = list(
        chain(*[dataset.patient_to_index[i] for i in train_patient_indx])
    )
    val_index = list(chain(*[dataset.patient_to_index[i] for i in val_patient_indx]))
    test_index = list(chain(*[dataset.patient_to_index[i] for i in test_patient_indx]))
    train_dataset = torch.utils.data.Subset(dataset, train_index)
    val_dataset = torch.utils.data.Subset(dataset, val_index)
    test_dataset = torch.utils.data.Subset(dataset, test_index)
    return train_dataset, val_dataset, test_dataset


tasks = \
[
    "mortality",
    "readmission",


    ]
train_ratios = \
[


    1.0
]

device = torch.device('cuda:6' if torch.cuda.is_available() else 'cpu')

for task in tasks:
    print("task: ", task)
    if task == "mortality" or task == "readmission":
        with open(f'/shared/eng/pj20/kelpie_exp_data/ehr_data/mimic3_{task}.pkl', 'rb') as f:
            sample_dataset = pickle.load(f)
    else:
        with open(f'/data/pj20/exp_data/ccscm_ccsproc/sample_dataset_mimic3_{task}_th015.pkl', 'rb') as f:
            sample_dataset = pickle.load(f)
    for train_ratio in train_ratios:

        if task != "drugrec":
            models = [RNN, Transformer, RETAIN]
        else:
            models = [


                GAMENet
                ]


        results = defaultdict(list)

        for i in range(1):
            print("train_ratio: ", train_ratio)
            train_dataset, val_dataset, test_dataset = split_by_patient(sample_dataset, [0.8, 0.1, 0.1], train_ratio=train_ratio, seed=528)
            train_loader = get_dataloader(train_dataset, batch_size=64, shuffle=True)
            val_loader = get_dataloader(val_dataset, batch_size=64, shuffle=False)
            test_loader = get_dataloader(test_dataset, batch_size=64, shuffle=False)
            for model_ in models:
                if task == "mortality" or task == "readmission":
                    model = model_(
                        dataset=sample_dataset,
                        feature_keys=["conditions", "procedures", "drugs"],
                        label_key="label",
                        mode="binary",
                    )

                    trainer = Trainer(model=model, device=device, metrics=["pr_auc", "roc_auc", "accuracy", "f1", "jaccard"], output_path="ehr_training_result")
                    trainer.train(
                        train_dataloader=train_loader,
                        val_dataloader=val_loader,
                        epochs=30,
                        monitor="accuracy",
                    )

                elif task == "lenofstay":
                    model = model_(
                        dataset=sample_dataset,
                        feature_keys=["conditions", "procedures"],
                        label_key="label",
                        mode="multiclass",
                    )


                    trainer = Trainer(model=model, device=device, metrics=["roc_auc_weighted_ovr", "cohen_kappa", "accuracy", "f1_weighted"])
                    trainer.train(
                        train_dataloader=train_loader,
                        val_dataloader=val_loader,
                        epochs=50,
                        monitor="roc_auc_weighted_ovr",
                    )

                elif task == "drugrec":
                    try:
                        model = model_(
                            dataset=sample_dataset,
                            feature_keys=["conditions", "procedures"],
                            label_key="drugs",
                            mode="multilabel",
                        )
                    except:
                        model = model_(dataset=sample_dataset)


                    trainer = Trainer(model=model, device=device, metrics=["pr_auc_samples", "roc_auc_samples", "f1_samples", "jaccard_samples"])
                    try:
                        trainer.train(
                            train_dataloader=train_loader,
                            val_dataloader=val_loader,
                            epochs=50,
                            monitor="pr_auc_samples",
                        )

                    except:
                        try:
                            results[model_.__name__].append(trainer.evaluate(val_loader))
                        except:
                            continue
                        continue

                results[model_.__name__].append(trainer.evaluate(val_loader))


        avg_results = defaultdict(dict)

        for k, v in results.items():
            for k_, v_ in v[0].items():
                avg_results[k][k_] = sum([vv[k_] for vv in v]) / len(v)


        import numpy as np

        variation_results = defaultdict(dict)

        for k, v in results.items():
            for k_, v_ in v[0].items():
                variation_results[k][k_] = np.std([vv[k_] for vv in v])


        print(avg_results)
        print(variation_results)
        with open(f"./ehr_training_result/avg_results_{task}_{train_ratio}.json", "w") as f:
            json.dump(avg_results, f, indent=6)
        with open(f"./ehr_training_result/variation_results_{task}_{train_ratio}.json", "w") as f:
            json.dump(variation_results, f, indent=6)
