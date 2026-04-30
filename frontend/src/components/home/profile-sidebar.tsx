import { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUser, faXmark, faRightFromBracket } from "@fortawesome/free-solid-svg-icons";

import HistoryTab from "./history-tab";
import ConfigTab from "./config-tab";
import { logout } from "../../redux/userSlice";

interface ProfileSidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export default function ProfileSidebar(props: ProfileSidebarProps) {
  const { sidebarOpen, setSidebarOpen } = props;
  const [activeTab, setActiveTab] = useState<string>("history");

  const dispatch = useDispatch();
  const user = useSelector((state: any) => state.user);

  const handleLogout = () => {
    dispatch(logout());
  };

  return (
    <div>
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-gray-900 bg-opacity-50"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <div
        className={`fixed w-full sm:w-[500px] h-full flex flex-col px-6 py-8
                    transition-all duration-300 bg-secondary dark:bg-[#0E0C16]
                    shadow-[-2px_0_4px_-1px_rgba(0,0,0,0.5)] dark:shadow-[-2px_0_4px_-1px_rgba(255,255,255,0.5)]
                    ${
                      sidebarOpen
                        ? "right-0"
                        : "-right-[100%] sm:-right-[510px]"
                    }`}
      >
        {user.isAuthenticated ? (
          <>
            <div className="flex w-full justify-between items-center px-2 ms-2 md:ms-0">
              <div className="flex w-[calc(100%-50px)] items-center">
                <div
                  className={`flex justify-center items-center p-2 sm:p-3 rounded-full
                                    transition-all duration-200 cursor-pointer text-gray-700 text-white
                                    bg-gradient-primary`}
                >
                  <FontAwesomeIcon icon={faUser} />
                </div>
                <h2 className="ms-2 text-lg text-gray-700 dark:text-white truncate">
                  {user.email.split("@")[0]}
                </h2>
              </div>
              <div
                className="flex justify-center items-center cursor-pointer text-gray-700 dark:text-white"
                onClick={() => setSidebarOpen(false)}
              >
                <FontAwesomeIcon icon={faXmark} />
              </div>
            </div>
            <div className="flex mt-6">
              <button
                onClick={() => setActiveTab("history")}
                className={`px-6 py-2 text-xl font-bold
                ${
                  activeTab === "history"
                    ? "border-b-2 border-gray-700 dark:border-white text-gray-700 dark:text-white"
                    : "text-gray-400 hover:text-gray-700 dark:hover:text-white"
                }`}
              >
                History
              </button>
              <button
                onClick={() => setActiveTab("config")}
                className={`px-6 py-2 text-xl font-bold
                ${
                  activeTab === "config"
                    ? "border-b-2 border-gray-700 dark:border-white text-gray-700 dark:text-white"
                    : "text-gray-400 hover:text-gray-700 dark:hover:text-white"
                }`}
              >
                Config
              </button>
            </div>
            {activeTab === "history" ? <HistoryTab /> : <ConfigTab />}

            {/* Logout */}
            <div className="mt-auto pt-4 pb-2 border-t border-gray-200 dark:border-dark-border">
              <button
                className="flex items-center gap-2 px-4 py-2 text-sm text-gray-500 dark:text-gray-400
                  hover:text-gray-700 dark:hover:text-white transition-colors duration-200"
                onClick={handleLogout}
              >
                <FontAwesomeIcon icon={faRightFromBracket} />
                <span>Sign out</span>
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
