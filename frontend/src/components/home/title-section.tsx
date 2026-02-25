export default function TitleSection() {
  return (
    <div className="animate-slide-up">
      <h1 className="w-full text-center mb-3 text-3xl md:text-5xl leading-tight font-bold text-gray-800 dark:text-white tracking-tight text-balance">
        Fully Permissionless and Incentivized{" "}
        <span className="font-extrabold bg-gradient-primary bg-clip-text text-transparent">
          Web&nbsp;Operator
        </span>
      </h1>
      <h2 className="w-full text-center mb-3 text-xl md:text-2xl font-medium text-gray-600 dark:text-gray-300 tracking-tight">
        Powered by&nbsp;
        <a
          href="https://bittensor.com"
          className="inline-block border-b-2 border-transparent hover:border-current transition-all duration-300"
        >
          <span className="font-bold bg-gradient-secondary bg-clip-text text-transparent">
            Bittensor
          </span>
        </a>
      </h2>
      <p className="w-full text-center mb-10 text-base md:text-lg font-normal text-gray-500 dark:text-gray-400">
        What can I help you with?
      </p>
    </div>
  );
}
