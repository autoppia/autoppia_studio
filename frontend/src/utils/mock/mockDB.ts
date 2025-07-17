import {
  faChartSimple,
  faCartShopping,
  faShield,
  faDollar,
  faWallet,
  faDatabase,
  faTicket,
  faPaw
} from "@fortawesome/free-solid-svg-icons";

export const websites = [
  {
    title: "Amazon",
    url: "https://amazon.com",
    favicon: "/assets/images/favicons/amazon.png",
  },
  {
    title: "Autoppia",
    url: "https://autoppia.com",
    favicon: "/assets/images/favicons/autoppia.png",
  },
  {
    title: "Autoppia Dashboard",
    url: "https://app.autoppia.com",
    favicon: "/assets/images/favicons/autoppia.png",
  },
  {
    title: "Bitrefill",
    url: "https://www.bitrefill.com",
    favicon: '/assets/images/favicons/bitrefill.png',
  },
  {
    title: "Bittensor",
    url: "https://www.bittensor.ai",
    favicon: "/assets/images/favicons/bittensor.png"
  },
  {
    title: "Google Search",
    url: "https://google.com",
    favicon: "/assets/images/favicons/google.png"
  },
  {
    title: "Google Maps",
    url: "https://maps.google.com",
    favicon: '/assets/images/favicons/maps.google.png'
  },
  {
    title: "Pokemon Showdown",
    url: "https://pokemonshowdown.com",
    favicon: "/assets/images/favicons/pokemonshowdown.png"
  },
  {
    title: "Tao App",
    url: "https://www.tao.app",
    favicon: "/assets/images/favicons/taoapp.png"
  },
  {
    title: "Tao Stats",
    url: "https://taostats.io",
    favicon: "/assets/images/favicons/taostats.png"
  },
  {
    title: "Tao Yield",
    url: "https://www.taoyield.com",
    favicon: "/assets/images/favicons/taoyield.png",
  },
];

export const bittensorPrompts = [
  {
    title: "Subnet36 Key Stats in Bittensor.ai",
    prompt: "Find the subnet 36 page, go to the detail page, and tell me the key alpha stats.",
    url: "https://www.bittensor.ai",
    icon: faChartSimple,
  },
  {
    title: "Top SN36 Validators by APY in Taoyield",
    prompt: "Which are the top 5 validators with the highest APY in a 30-day period?",
    url: "https://www.taoyield.com",
    icon: faShield,
  },
  {
    title: "Ask Savant in Tao.app",
    prompt: "Ask the assistant what the price of Autoppia is and how many emissions they have.",
    url: "https://www.tao.app/assistant",
    icon: faDollar,
  },
  {
    title: "Portfolio Wallet Creation in Taostats",
    prompt: "Sign up anonymously and create a new portfolio wallet for {ADDRESS}, then tell me the balance and TAO staked in the root.",
    url: "https://taostats.io",
    icon: faWallet,
  }
];

export const generalPrompts = [
  {
    title: "Amazon Full Checkout",
    prompt: "Search for a red shirt, add it to the cart, proceed to checkout, log in, and fill in the address.",
    url: "https://www.amazon.com",
    icon: faCartShopping,
  },
  {
    title: "Autoppia Platform Demo",
    prompt: "Edit the PostgreSQL database integration and change the port to the existing port plus one.",
    url: "https://app.autoppia.com",
    icon: faDatabase,
  },
  {
    title: "Bitrefill Steam $50 Coupon",
    prompt: "Find a Steam coupon for 50 dollars and add it to the cart, then go to the cart details (do not change the currency).",
    url: "https://www.bitrefill.com",
    icon: faTicket,
  },
  {
    title: "Pokemon Match",
    prompt: "Play one match of Pokémon against a random opponent.",
    url: "https://pokemonshowdown.com",
    icon: faPaw,
  }
];
