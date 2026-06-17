import { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { setUser } from "../../redux/userSlice";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

export default function ConfigTab() {
  const user = useSelector((state: any) => state.user);
  const [instructions, setInstructions] = useState<string>(user.instructions);

  const dispatch = useDispatch();

  const handleSubmit = async () => {
    try {
      const response = await fetch(`${apiUrl}/user/update`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: user.email,
          instructions: instructions,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        dispatch(
          setUser({
            email: data.user.email,
            instructions: data.user.instructions,
          })
        );
        setInstructions(data.user.instructions);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <>
      <div className="flex-grow w-full">
        <h3 className="font-semibold text-sm text-gray-700 dark:text-white mb-2">
          Custom Instructions
        </h3>
        <textarea
          rows={4}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          className="w-full p-3 rounded-xl outline-none text-sm
            bg-gray-50 dark:bg-dark-surface border border-gray-200 dark:border-dark-border
            text-gray-700 dark:text-gray-200 placeholder:text-gray-400
            focus:border-gray-300 dark:focus:border-gray-600 focus:shadow-soft
            transition-all duration-300 resize-none"
        />
      </div>
      {instructions !== user.instructions && (
        <div className="flex justify-end gap-3 mt-3">
          <button
            className="px-5 py-2 text-sm bg-gradient-primary text-white rounded-xl font-medium shadow-glow hover:shadow-glow-lg transition-all duration-300"
            onClick={handleSubmit}
          >
            Save
          </button>
          <button
            className="px-5 py-2 text-sm bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
              text-gray-600 dark:text-gray-300 rounded-xl font-medium hover:bg-gray-50 dark:hover:bg-dark-border transition-all duration-300"
            onClick={() => setInstructions(user.instructions)}
          >
            Cancel
          </button>
        </div>
      )}
    </>
  );
}
