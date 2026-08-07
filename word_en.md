# 毕业答辩问答

---

## 答辩问答

| 问题 | 答案 | 中文 |
|------|------|------|
|什么是F1分数？请解释一下F1分数。\nWhat is the F1 score? Please explain it.|For a binary classifier, the output is usually a probability score. We compare this score with a threshold, which is usually 0.5. If the probability score is higher than the threshold, we predict the sample as positive. Otherwise, we predict it as negative.\nThen, we compare the predicted label with the real label. This gives us four possible outcomes: true positive (TP), false positive (FP), true negative (TN), and false negative (FN).\nThe F1 score is calculated from precision and recall.\nPrecision = TP / (TP + FP)\nRecall = TP / (TP + FN)\nThe F1 score is the harmonic mean of precision and recall:\nF1 = 2 × (Precision × Recall) / (Precision + Recall)\nIt can also be written as:\nF1 = 2TP / (2TP + FP + FN)|对于二分类器，输出通常是一个概率分数。我们将这个分数与一个阈值（通常是0.5）进行比较：如果概率分数高于阈值，就把该样本预测为正类；否则预测为负类。\n然后，把预测标签与真实标签进行比较，这样会得到四种可能的结果：真阳性(TP)、假阳性(FP)、真阴性(TN)、假阴性(FN)。\nF1分数由精确率（Precision）和召回率（Recall）计算得出。\n精确率 = TP / (TP + FP)\n召回率 = TP / (TP + FN)\nF1分数是精确率和召回率的调和平均数：\nF1 = 2 × (精确率 × 召回率) / (精确率 + 召回率)\n也可以写成：\nF1 = 2TP / (2TP + FP + FN)|
