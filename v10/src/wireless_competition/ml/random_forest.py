"""干扰分类器 — 随机森林 + 置信度门控 + OOD 检测。

第一版 ML 模型：手工特征 + 随机森林。
低计算量、CPU 可实时运行、对数据量要求低。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler, LabelEncoder

from .dataset import InterferenceDataset


class InterferenceClassifier:
    """干扰分类器。

    封装：特征标准化 → 随机森林 → 概率校准 → 置信度门控。
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 12,
        min_samples_leaf: int = 5,
        confidence_threshold: float = 0.6,
        random_state: int = 42,
    ):
        """
        Args:
            n_estimators: 随机森林树数量。
            max_depth: 最大树深度。
            min_samples_leaf: 叶节点最小样本数。
            confidence_threshold: 低于此置信度的预测视为不可靠。
            random_state: 随机种子。
        """
        self.confidence_threshold = confidence_threshold

        self._scaler = StandardScaler()
        self._label_encoder = LabelEncoder()
        self._rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=-1,
        )
        self._calibrated: Optional[CalibratedClassifierCV] = None
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    @property
    def classes_(self) -> np.ndarray:
        return self._label_encoder.classes_

    @property
    def feature_importances_(self) -> np.ndarray:
        return self._rf.feature_importances_

    def fit(self, dataset: InterferenceDataset) -> "InterferenceClassifier":
        """训练分类器。

        Args:
            dataset: 训练数据集。

        Returns:
            self（支持链式调用）。
        """
        X = dataset.X
        y_str = dataset.y

        # 标签编码
        y = self._label_encoder.fit_transform(y_str)

        # 特征标准化
        X_scaled = self._scaler.fit_transform(X)

        # 训练随机森林
        self._rf.fit(X_scaled, y)

        # 概率校准（Platt scaling）
        try:
            self._calibrated = CalibratedClassifierCV(
                self._rf, method="sigmoid", cv=5
            )
            self._calibrated.fit(X_scaled, y)
        except Exception:
            # 样本太少时校准可能失败，退回到未校准
            self._calibrated = None

        self._trained = True
        return self

    def predict(self, features: np.ndarray) -> dict:
        """预测干扰类型。

        Args:
            features: 特征向量或矩阵 (n_samples, n_features)。

        Returns:
            {
                "class": str,           # 预测类别
                "confidence": float,     # 最大概率 (0-1)
                "all_probs": dict,       # {类别: 概率}
                "is_ood": bool,          # 是否判定为分布外
                "reliable": bool,        # 置信度是否达标
            }
        """
        if not self._trained:
            raise RuntimeError("Classifier not trained. Call fit() first.")

        X = np.atleast_2d(np.asarray(features, dtype=np.float64))
        X_scaled = self._scaler.transform(X)

        # 获取概率
        if self._calibrated is not None:
            probs = self._calibrated.predict_proba(X_scaled)
        else:
            probs = self._rf.predict_proba(X_scaled)

        row = X_scaled[0] if len(X_scaled) == 1 else None
        if row is not None:
            probs = probs[0]

        max_idx = int(np.argmax(probs))
        confidence = float(probs[max_idx])
        class_name = str(self._label_encoder.inverse_transform([max_idx])[0])

        # OOD 检测：最大概率低于阈值 → 视为未知
        is_ood = confidence < self.confidence_threshold

        # 所有类别概率
        all_probs = {}
        for i, p in enumerate(probs if len(probs.shape) == 1 else probs.ravel()):
            all_probs[str(self._label_encoder.inverse_transform([i])[0])] = float(p)

        return {
            "class": "unknown" if is_ood else class_name,
            "confidence": confidence,
            "all_probs": all_probs,
            "is_ood": is_ood,
            "reliable": not is_ood,
        }

    def predict_batch(self, features_matrix: np.ndarray) -> list[dict]:
        """批量预测。"""
        results = []
        for i in range(len(features_matrix)):
            results.append(self.predict(features_matrix[i]))
        return results

    def evaluate(self, dataset: InterferenceDataset) -> dict:
        """在测试集上评估分类器性能。

        Returns:
            {
                "accuracy": float,
                "macro_f1": float,
                "confusion_matrix": list[list[int]],
                "per_class": {class: {"precision", "recall", "f1"}},
                "ood_rate": float,     # OOD 触发率
                "mean_confidence": float,
            }
        """
        from sklearn.metrics import (
            accuracy_score, f1_score, precision_recall_fscore_support,
            confusion_matrix,
        )

        X = dataset.X
        y_true_str = dataset.y
        y_true = self._label_encoder.transform(y_true_str)

        X_scaled = self._scaler.transform(X)
        y_pred = self._rf.predict(X_scaled)
        if self._calibrated is not None:
            probs = self._calibrated.predict_proba(X_scaled)
        else:
            probs = self._rf.predict_proba(X_scaled)

        confidences = np.max(probs, axis=1)
        ood_mask = confidences < self.confidence_threshold

        accuracy = float(accuracy_score(y_true, y_pred))
        macro_f1 = float(f1_score(y_true, y_pred, average="macro"))
        cm = confusion_matrix(y_true, y_pred).tolist()

        # 每类指标
        prec, rec, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, labels=range(len(self.classes_)), zero_division=0
        )
        per_class = {}
        for i, name in enumerate(self.classes_):
            per_class[str(name)] = {
                "precision": float(prec[i]),
                "recall": float(rec[i]),
                "f1": float(f1[i]),
            }

        return {
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "confusion_matrix": cm,
            "class_names": [str(c) for c in self.classes_],
            "per_class": per_class,
            "ood_rate": float(np.mean(ood_mask)),
            "mean_confidence": float(np.mean(confidences)),
            "n_samples": len(y_true),
        }

    def save(self, path: str | Path) -> Path:
        """保存模型到文件。

        Args:
            path: 文件路径 (.joblib)。

        Returns:
            保存路径。
        """
        import joblib
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        bundle = {
            "scaler": self._scaler,
            "label_encoder": self._label_encoder,
            "rf": self._rf,
            "calibrated": self._calibrated,
            "confidence_threshold": self.confidence_threshold,
        }
        joblib.dump(bundle, path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "InterferenceClassifier":
        """从文件加载模型。"""
        import joblib
        bundle = joblib.load(Path(path))

        clf = cls(confidence_threshold=bundle["confidence_threshold"])
        clf._scaler = bundle["scaler"]
        clf._label_encoder = bundle["label_encoder"]
        clf._rf = bundle["rf"]
        clf._calibrated = bundle.get("calibrated")
        clf._trained = True
        return clf
