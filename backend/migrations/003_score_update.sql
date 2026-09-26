-- 모델을 바꿔 오늘의 기존 점수를 다시 계산한 시각입니다. 기록 자체는 보존합니다.
ALTER TABLE puzzles ADD COLUMN scores_updated_at timestamptz;
