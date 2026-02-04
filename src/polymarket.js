/**
 * Polymarket API Client
 * The boring but necessary part
 */

const POLYMARKET_API = 'https://clob.polymarket.com';
const GAMMA_API = 'https://gamma-api.polymarket.com';

/**
 * Fetch all active markets
 */
export async function getMarkets() {
  const response = await fetch(`${GAMMA_API}/markets?closed=false&limit=500`);
  const data = await response.json();
  return data;
}

/**
 * Get market by condition ID
 */
export async function getMarket(conditionId) {
  const response = await fetch(`${GAMMA_API}/markets/${conditionId}`);
  return response.json();
}

/**
 * Get orderbook for a token
 */
export async function getOrderbook(tokenId) {
  const response = await fetch(`${POLYMARKET_API}/book?token_id=${tokenId}`);
  return response.json();
}

/**
 * Get current prices for a market
 */
export async function getPrices(market) {
  try {
    const prices = {};
    
    for (const outcome of market.outcomes || []) {
      // Best bid/ask from CLOB
      const tokenId = outcome.token_id || market.tokens?.find(t => t.outcome === outcome)?.token_id;
      if (tokenId) {
        const book = await getOrderbook(tokenId);
        prices[outcome] = {
          bid: parseFloat(book.bids?.[0]?.price || 0),
          ask: parseFloat(book.asks?.[0]?.price || 1),
          mid: (parseFloat(book.bids?.[0]?.price || 0) + parseFloat(book.asks?.[0]?.price || 1)) / 2
        };
      }
    }
    
    return prices;
  } catch (e) {
    return null;
  }
}

/**
 * Search markets by keyword
 */
export async function searchMarkets(query) {
  const markets = await getMarkets();
  const q = query.toLowerCase();
  return markets.filter(m => 
    m.question?.toLowerCase().includes(q) ||
    m.description?.toLowerCase().includes(q)
  );
}

/**
 * Group related markets (same event, different dates/outcomes)
 */
export async function findRelatedMarkets(markets) {
  const groups = {};
  
  for (const market of markets) {
    // Extract base event (remove dates, specific outcomes)
    const baseEvent = extractBaseEvent(market.question || '');
    
    if (!groups[baseEvent]) {
      groups[baseEvent] = [];
    }
    groups[baseEvent].push(market);
  }
  
  // Only return groups with multiple markets (potential arb)
  return Object.entries(groups)
    .filter(([_, markets]) => markets.length > 1)
    .map(([event, markets]) => ({ event, markets }));
}

/**
 * Extract base event from question (remove dates, specific values)
 */
function extractBaseEvent(question) {
  return question
    .replace(/\b(by|before|after|in|on)\s+(january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}|\d{4})\b/gi, '')
    .replace(/\b\d{1,2}(st|nd|rd|th)?\b/gi, '')
    .replace(/\b(yes|no)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .substring(0, 50);
}
