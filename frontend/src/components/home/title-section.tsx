export default function TitleSection() {
  return (
    <>
      <h2 className="w-full text-center mb-4 text-3xl md:text-4xl leading-tight font-semibold text-gray-700 dark:text-white tracking-wide">
        Fully Permissionless and Incentivized{" "}
        <span className="font-extrabold bg-gradient-primary bg-clip-text text-transparent">
          Web&nbsp;Operator
        </span>
      </h2>
      <h2 className="w-full text-center mb-4 text-2xl md:text-[2rem] font-medium text-gray-700 dark:text-white tracking-wide">
        Powered by&nbsp;
        <a
          href="https://bittensor.com"
          className="text-gradient-secondary border-b-2 border-gray-700 dark:border-white"
        >
          <span className="font-bold bg-gradient-secondary bg-clip-text text-transparent">
            Bittensor
          </span>
        </a>
      </h2>
      <p className="w-full text-center mb-8 text-lg md:text-xl font-medium text-gray-600 dark:text-gray-300">
        What can I help you with?
      </p>
    </>
  );
}
