import { useState, FormEvent } from 'react';

interface InputFormProps {
  onSubmit: (message: string) => void;
  disabled: boolean;
}

export default function InputForm({ onSubmit, disabled }: InputFormProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSubmit(message.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full flex-1 flex flex-col">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="请输入需求描述，例如：游戏中需要开发一个战令活动..."
        disabled={disabled}
        className="flex-1 w-full p-4 border border-orange-200 rounded-lg resize-none
                   focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent
                   disabled:bg-orange-100 disabled:cursor-not-allowed
                   dark:bg-orange-900/30 dark:border-orange-700 dark:text-gray-100
                   dark:placeholder-gray-400"
      />
      <button
        type="submit"
        disabled={disabled || !message.trim()}
        className="shrink-0 mt-3 px-6 py-2.5 bg-orange-500 text-white rounded-lg font-medium
                   hover:bg-orange-600 transition-colors
                   disabled:bg-gray-400 disabled:cursor-not-allowed
                   dark:bg-orange-600 dark:hover:bg-orange-700"
      >
        {disabled ? '生成中...' : '开始生成文档'}
      </button>
    </form>
  );
}
