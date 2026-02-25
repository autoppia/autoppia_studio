import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

interface IconButtonProps {
  icon: any;
  className?: string;
  onClick?: () => void;
  disabled?: boolean;
}

export default function IconButton(props: IconButtonProps) {
  const { icon, className, onClick, disabled } = props;
  return (
    <div
      className={`flex justify-center items-center w-9 h-9 sm:w-10 sm:h-10 rounded-full
        transition-all duration-300 cursor-pointer text-gray-600
        border border-gray-200 hover:border-gray-300 hover:bg-gray-100 hover:shadow-soft
        ${disabled ? "opacity-40 cursor-not-allowed" : ""} ${className}`}
      onClick={disabled ? undefined : onClick}
    >
      <FontAwesomeIcon icon={icon} className="text-sm" />
    </div>
  );
}
