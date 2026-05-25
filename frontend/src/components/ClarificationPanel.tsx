import { useState, FormEvent } from 'react';

interface ClarificationItem {
  question: string;
  options: string[];
}

interface ClarificationPanelProps {
  questions: ClarificationItem[];
  onSubmit: (answers: string) => void;
  disabled: boolean;
}

export default function ClarificationPanel({ questions, onSubmit, disabled }: ClarificationPanelProps) {
  const [selections, setSelections] = useState<Record<number, string>>({});
  const [customInputs, setCustomInputs] = useState<Record<number, string>>({});

  const handleSelect = (qIndex: number, value: string) => {
    setSelections((prev) => ({ ...prev, [qIndex]: value }));
  };

  const handleCustomInput = (qIndex: number, value: string) => {
    setCustomInputs((prev) => ({ ...prev, [qIndex]: value }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const answerLines = questions.map((q, i) => {
      const selected = selections[i];
      if (selected === '__custom__') {
        return `${q.question}\n回答：${customInputs[i] || ''}`;
      }
      return `${q.question}\n回答：${selected || ''}`;
    });
    const combined = answerLines.join('\n\n');
    if (combined.trim() && !disabled) {
      onSubmit(combined);
    }
  };

  const allAnswered = questions.every((_, i) => {
    const sel = selections[i];
    if (!sel) return false;
    if (sel === '__custom__') return !!customInputs[i]?.trim();
    return true;
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <h3 className="font-medium text-gray-800 dark:text-gray-200">
        在继续生成文档之前，请回答以下问题：
      </h3>

      {questions.map((item, qIndex) => (
        <div key={qIndex} className="space-y-2 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <p className="font-medium text-gray-800 dark:text-gray-200">
            {qIndex + 1}. {item.question}
          </p>
          <div className="space-y-1 ml-4">
            {item.options.map((opt, oIndex) => (
              <label key={oIndex} className="flex items-start gap-2 cursor-pointer py-1">
                <input
                  type="radio"
                  name={`q-${qIndex}`}
                  value={opt}
                  checked={selections[qIndex] === opt}
                  onChange={() => handleSelect(qIndex, opt)}
                  className="mt-1 accent-blue-600"
                />
                <span className="text-gray-700 dark:text-gray-300">{opt}</span>
              </label>
            ))}
            <label className="flex items-start gap-2 cursor-pointer py-1">
              <input
                type="radio"
                name={`q-${qIndex}`}
                value="__custom__"
                checked={selections[qIndex] === '__custom__'}
                onChange={() => handleSelect(qIndex, '__custom__')}
                className="mt-1 accent-blue-600"
              />
              <span className="text-gray-700 dark:text-gray-300">其他</span>
            </label>
            {selections[qIndex] === '__custom__' && (
              <input
                type="text"
                value={customInputs[qIndex] || ''}
                onChange={(e) => handleCustomInput(qIndex, e.target.value)}
                placeholder="请输入您的答案..."
                className="ml-6 mt-1 w-full p-2 border border-gray-300 rounded
                           focus:outline-none focus:ring-2 focus:ring-blue-500
                           dark:bg-gray-800 dark:border-gray-600 dark:text-gray-100"
              />
            )}
          </div>
        </div>
      ))}

      <button
        type="submit"
        disabled={disabled || !allAnswered}
        className="px-6 py-2.5 bg-green-600 text-white rounded-lg font-medium
                   hover:bg-green-700 transition-colors
                   disabled:bg-gray-400 disabled:cursor-not-allowed
                   dark:bg-green-500 dark:hover:bg-green-600"
      >
        {disabled ? '提交中...' : '提交回答并继续生成'}
      </button>
    </form>
  );
}
