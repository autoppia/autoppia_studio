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
      className={`flex justify-center items-center p-2 sm:p-3 rounded-full transition-all duration-200 cursor-pointer text-gray-700 border border-gray-300 hover:bg-gray-300 ${className}`}
      onClick={disabled ? undefined : onClick}
    >
      <FontAwesomeIcon icon={icon} />
    </div>
  );
}
