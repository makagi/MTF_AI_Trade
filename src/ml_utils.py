import numpy as np
import pandas as pd

class PurgedTimeSeriesSplit:
    """
    未来情報の漏洩（Lookahead Bias）を防ぐための時系列分割交差検証。
    訓練データ(Train)と検証データ(Test)の間に、ラベル判定期間（最大保持期間）に
    相当するパージ（ギャップ）を設ける。
    """
    def __init__(self, n_splits=5, purge_period=24, embargo_period=0):
        self.n_splits = n_splits
        self.purge_period = purge_period
        self.embargo_period = embargo_period

    def split(self, X, y=None, groups=None):
        """
        X: データセット
        戻り値: (train_idx, test_idx) のジェネレータ
        """
        n_samples = len(X)
        indices = np.arange(n_samples)
        
        # データを (n_splits + 1) 分割
        fold_size = n_samples // (self.n_splits + 1)
        
        for i in range(self.n_splits):
            # Trainは開始時点から test_start まで成長していく (Expanding window)
            test_start = (i + 1) * fold_size
            test_end = (i + 2) * fold_size
            if i == self.n_splits - 1:
                test_end = n_samples
            
            # パージ: TestのデータがTrainのラベル評価に漏れないよう、Trainの末尾を削る
            train_end = test_start - self.purge_period
            
            if train_end <= 0:
                continue
                
            train_indices = indices[0:train_end]
            
            # エンバーゴ: (通常はTestの後にTrainが続く場合に用いるが、前進法でも安全のため追加可能)
            actual_test_start = test_start + self.embargo_period
            
            if actual_test_start >= test_end:
                continue
                
            test_indices = indices[actual_test_start:test_end]
            
            yield train_indices, test_indices

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits

if __name__ == "__main__":
    # テスト
    X = np.arange(100)
    cv = PurgedTimeSeriesSplit(n_splits=3, purge_period=10)
    for i, (train_idx, test_idx) in enumerate(cv.split(X)):
        print(f"Fold {i}:")
        print(f"  Train: [{train_idx[0]} ... {train_idx[-1]}] (size {len(train_idx)})")
        print(f"  Test:  [{test_idx[0]} ... {test_idx[-1]}] (size {len(test_idx)})")
        gap = test_idx[0] - train_idx[-1] - 1
        print(f"  Gap (Purge): {gap}")
