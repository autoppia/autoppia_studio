import { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { setUser } from "../../redux/userSlice";

const apiUrl = process.env.REACT_APP_API_URL;

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
      <div className="flex-grow px-2 mt-6 w-full">
        <h2 className="font-bold text-md text-gray-700 dark:text-white">
          Custom Instructions
        </h2>
        <textarea
          rows={4}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          className="w-full mt-2 p-2 rounded-lg outline-none border border-gray-500"
        />
      </div>
      {instructions !== user.instructions && (
        <div className="flex px-2 justify-end gap-4">
          <button
            className="px-4 py-1 text-sm bg-gradient-primary text-white rounded-full"
            onClick={handleSubmit}
          >
            Save
          </button>
          <button
            className="px-4 py-1 text-sm bg-white border border-gray-500 text-gray-700 rounded-full"
            onClick={() => setInstructions(user.instructions)}
          >
            Cancel
          </button>
        </div>
      )}
    </>
  );
}
