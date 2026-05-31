export default function TitleSection() {
  return (
    <div className="animate-slide-up">
      <h1 className="w-full text-center mb-3 text-3xl md:text-5xl leading-tight font-bold text-gray-800 dark:text-white tracking-tight text-balance">
        Automata{" "}
        <span className="font-extrabold bg-gradient-primary bg-clip-text text-transparent">
          Operator
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
    </div>
  );
}
