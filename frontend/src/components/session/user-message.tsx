interface UserMessageProps {
  content?: string;
}

export default function UserMessage(props: UserMessageProps) {
  const { content } = props;
  return (
    <div className="w-full flex justify-end mb-4 animate-fade-in">
      <div className="max-w-[85%] text-gray-800 dark:text-white rounded-2xl rounded-br-md py-2.5 px-4 bg-gradient-primary text-white text-sm leading-relaxed shadow-glow">
        {content}
      </div>
    </div>
  );
}
