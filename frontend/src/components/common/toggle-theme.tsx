import { faCircleHalfStroke } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

function ToggleTheme() {
  const darkThemeHandler = () => {
    const isDark = document.documentElement.classList.toggle("dark");
    try {
      localStorage.setItem("theme", isDark ? "dark" : "light");
    } catch {
      /* ignore storage errors */
    }
  };
  return (
    <div
      className="flex justify-center items-center w-9 h-9 sm:w-10 sm:h-10 rounded-full
                  transition-all duration-300 cursor-pointer text-gray-600 dark:text-white
                  border border-gray-200 dark:border-dark-border hover:border-gray-300
                  hover:bg-gray-100 dark:hover:bg-dark-surface hover:shadow-soft"
      onClick={darkThemeHandler}
    >
      <FontAwesomeIcon icon={faCircleHalfStroke} className="text-sm" />
    </div>
  );
}

export default ToggleTheme;
