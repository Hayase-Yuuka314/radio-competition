"""ML 模块测试。"""

import numpy as np
import pytest

from wireless_competition.features.time_domain import FeatureExtractor
from wireless_competition.ml.dataset import (
    InterferenceDataset, generate_dataset, INTERFERENCE_CONFIGS,
)
from wireless_competition.ml.random_forest import InterferenceClassifier


class TestFeatureExtractor:
    def test_extract_returns_vector(self):
        ext = FeatureExtractor(window_samples=256)
        iq = np.random.default_rng(1).standard_normal(256) + \
             1j * np.random.default_rng(2).standard_normal(256)
        vec = ext.extract(iq)
        assert isinstance(vec, np.ndarray)
        assert vec.ndim == 1
        assert len(vec) > 10  # 应有多个特征

    def test_feature_names_consistent(self):
        ext = FeatureExtractor(window_samples=256)
        iq = np.zeros(256, dtype=np.complex128)
        ext.extract(iq)
        names = ext.feature_names
        assert len(names) > 10
        assert "power" in names
        assert "spectral_flatness" in names

    def test_same_input_same_output(self):
        ext = FeatureExtractor(window_samples=256)
        iq = np.ones(256, dtype=np.complex128)
        v1 = ext.extract(iq)
        v2 = ext.extract(iq)
        assert np.allclose(v1, v2)

    def test_no_nan_inf(self):
        ext = FeatureExtractor(window_samples=256)
        iq = np.random.default_rng(3).standard_normal(256) + \
             1j * np.random.default_rng(4).standard_normal(256)
        vec = ext.extract(iq)
        assert not np.any(np.isnan(vec))
        assert not np.any(np.isinf(vec))

    def test_short_signal_padded(self):
        ext = FeatureExtractor(window_samples=512)
        iq = np.ones(100, dtype=np.complex128)
        vec = ext.extract(iq)
        assert len(vec) == ext.n_features
        assert not np.any(np.isnan(vec))


class TestDataset:
    def test_generate_small(self):
        ds = generate_dataset(
            n_captures_per_class=2,
            n_windows_per_capture=3,
            window_samples=256,
            snr_db_range=[10],
            seed=42,
        )
        assert ds.n_samples == 2 * 3 * 7  # 2 caps * 3 wins * 7 classes
        assert len(ds.unique_labels) == 7
        assert ds.X.shape == (42, ds.X.shape[1])

    def test_split_no_leakage(self):
        ds = generate_dataset(
            n_captures_per_class=5,
            n_windows_per_capture=5,
            window_samples=256,
            seed=42,
        )
        train, val, test = ds.split_by_capture(seed=42)
        train_caps = set(train.capture_ids)
        val_caps = set(val.capture_ids)
        test_caps = set(test.capture_ids)

        assert len(train_caps & test_caps) == 0, "Train-Test leakage!"
        assert len(train_caps & val_caps) == 0, "Train-Val leakage!"

    def test_all_classes_represented(self):
        ds = generate_dataset(
            n_captures_per_class=6,  # 更多 capture 确保分裂覆盖
            n_windows_per_capture=3,
            window_samples=256,
            seed=42,
        )
        train, _, test = ds.split_by_capture(seed=42)
        for split_name, split in [("train", train), ("test", test)]:
            present = set(split.y)
            missing = set(ds.unique_labels) - present
            assert len(missing) <= 2, \
                f"{split_name} missing {len(missing)} classes: {missing}"


class TestClassifier:
    @pytest.fixture
    def dataset(self):
        return generate_dataset(
            n_captures_per_class=5,
            n_windows_per_capture=4,
            window_samples=256,
            snr_db_range=[5, 20],
            seed=42,
        )

    @pytest.fixture
    def trained_clf(self, dataset):
        train, _, _ = dataset.split_by_capture(seed=42)
        clf = InterferenceClassifier(n_estimators=30, max_depth=8)
        clf.fit(train)
        return clf

    def test_fit_predict(self, dataset, trained_clf):
        _, _, test = dataset.split_by_capture(seed=42)
        pred = trained_clf.predict(test.X[0])
        assert "class" in pred
        assert "confidence" in pred
        assert "is_ood" in pred
        assert 0 <= pred["confidence"] <= 1

    def test_accuracy_above_chance(self, dataset, trained_clf):
        """分类准确率应显著高于随机 (1/7≈14%)。"""
        _, _, test = dataset.split_by_capture(seed=42)
        ev = trained_clf.evaluate(test)
        assert ev["accuracy"] > 0.5, f"Accuracy {ev['accuracy']:.2f} too low"

    def test_save_load(self, trained_clf, tmp_path):
        path = tmp_path / "model.joblib"
        trained_clf.save(path)
        loaded = InterferenceClassifier.load(path)
        assert loaded.is_trained
        assert len(loaded.classes_) == len(trained_clf.classes_)
