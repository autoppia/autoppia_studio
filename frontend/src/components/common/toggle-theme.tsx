import { faCircleHalfStroke } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

function ToggleTheme() {
  const darkThemeHandler = () => {
    document.documentElement.classList.toggle("dark");
  };
  return (
    <div
      className="flex justify-center items-center p-2 sm:p-3 rounded-full
                  transition-all duration-200 cursor-pointer text-gray-700 dark:text-white
                  border border-gray-300 hover:bg-gray-300 ms-1 sm:ms-3"
      onClick={darkThemeHandler}
    >
      <FontAwesomeIcon icon={faCircleHalfStroke} />
    </div>
  );
}

export default ToggleTheme;
