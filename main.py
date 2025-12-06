# Fashion Bot with Outfit Coordination
import logging
import asyncio
import json
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from config import (
    TELEGRAM_BOT_TOKEN,
    OPENROUTER_API_KEY, 
    SERPAPI_KEY,
    AI_MODEL,
    AI_BASE_URL
)


class OutfitCoordinator:
    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.outfit_context = []
    
    async def search_outfit(self, user_query, plan, searcher):
        categories = plan.get("categories", [])
        brands_map = plan.get("brands_for_categories", {})
        budget = plan.get("budget_limit")
        
        # Save brands_map for use in _get_search_order
        self.brands_map = brands_map
        
        self.outfit_context = []
        results = []
        search_order = self._get_search_order(categories)
        
        for i, category in enumerate(search_order):
            logger.info(f"Searching for {category} (step {i+1}/{len(search_order)})")
            
            brands = brands_map.get(category, ["any"])
            query = await self._create_search_query(category, brands, user_query, self.outfit_context, budget)
            
            logger.info(f"Search query: '{query}'")
            
            try:
                search_results = await searcher.search_serpapi(query, 10)
                
                if search_results:
                    # Filter results
                    filtered = self._filter_results(search_results, brands, self.outfit_context)
                    
                    if filtered:
                        logger.info(f"Filtered {len(search_results)} -> {len(filtered)} items")
                        best_item = await self._select_best_item(filtered, category, brands, user_query, self.outfit_context, budget)
                    else:
                        logger.warning(f"All items filtered for {category}")
                        best_item = None
                    
                    # Try alternative searches if nothing found
                    if not best_item:
                        logger.info(f"Trying alternative queries for {category}")
                        best_item = await self._try_alternatives(category, brands, user_query, self.outfit_context, searcher)
                    
                    if best_item:
                        best_item['category'] = category
                        best_item['category_ru'] = searcher.get_display_name(category)
                        results.append(best_item)
                        
                        # Analyze found item
                        details = await self._analyze_item(best_item)
                        
                        self.outfit_context.append({
                            'category': category,
                            'title': best_item.get('title', ''),
                            'price': best_item.get('price', 'N/A'),
                            'source': best_item.get('source', ''),
                            'details': details
                        })
                        
                        logger.info(f"Selected: {best_item.get('title', '')[:50]}")
                        logger.info(f"Price: {best_item.get('price', 'N/A')} | Style: {details.get('style')} | Color: {details.get('color')}")
                    else:
                        logger.warning(f"Failed to find {category}")
                else:
                    logger.warning(f"No results for {category}")
                    best_item = await self._try_alternatives(category, brands, user_query, self.outfit_context, searcher)
                    
                    if best_item:
                        best_item['category'] = category
                        best_item['category_ru'] = searcher.get_display_name(category)
                        results.append(best_item)
                        
                        details = await self._analyze_item(best_item)
                        self.outfit_context.append({
                            'category': category,
                            'title': best_item.get('title', ''),
                            'price': best_item.get('price', 'N/A'),
                            'source': best_item.get('source', ''),
                            'details': details
                        })
                        
                        logger.info(f"Found via alternative: {best_item.get('title', '')[:50]}")
                
                await asyncio.sleep(0.8)
                
            except Exception as e:
                logger.error(f"Search error for {category}: {e}")
                continue
        
        logger.info(f"Outfit ready: {len(results)} items")
        
        # Final check
        if len(results) >= 2:
            harmony = await self._check_harmony(results, user_query, budget)
            if not harmony["is_good"]:
                logger.warning(f"Outfit issues: {harmony['reason']}")
        
        return results
    
    async def _create_search_query(self, category, brands, user_query, context, budget):
        context_info = "First item in outfit"
        style_hints = ""
        price_hints = ""
        
        if context:
            items = []
            colors = []
            styles = []
            prices = []
            
            for item in context:
                title = item.get('title', '')
                price_str = item.get('price', '')
                details = item.get('details', {})
                
                if details.get('color') != 'unknown':
                    colors.append(details.get('color'))
                if details.get('style'):
                    styles.append(details.get('style'))
                
                price_match = re.search(r'[\d.,]+', str(price_str))
                if price_match:
                    try:
                        price = float(price_match.group().replace(',', ''))
                        prices.append(price)
                    except:
                        pass
                
                items.append(f"- {item.get('category', '')}: {title[:60]} ({price_str})")
                items.append(f"  Style: {details.get('style')} | Color: {details.get('color')}")
            
            context_info = "\n".join(items)
            
            if colors:
                unique_colors = list(set(colors))
                style_hints = f"Colors in outfit: {unique_colors}"
            
            if styles:
                main_style = max(set(styles), key=styles.count)
                style_hints += f" | Main style: {main_style}"
            
            if prices:
                avg_price = sum(prices) / len(prices)
                price_hints = f"Average price: ${avg_price:.0f}"
        
        brand_info = ""
        if brands and brands[0] != "any":
            brand = brands[0]
            brand_info = f"Required brand: {brand}"
            
            if brand == "opium_style":
                brand_info += " (dark gothic style)"
            elif brand == "acne studios":
                brand_info += " (scandinavian minimalism)"
            elif brand == "maison margiela":
                brand_info += " (avant-garde design)"
        
        budget_info = ""
        if budget and context:
            spent = sum(prices) if prices else 0
            left = budget - spent
            budget_info = f"Budget: ${budget}, spent: ${spent:.0f}, remaining: ${left:.0f}"
        
        prompt = f"""
        Create a search query for Google Shopping.
        
        User looking for: "{user_query}"
        Need category: {category}
        {brand_info}
        {budget_info}
        
        Found in outfit:
        {context_info}
        
        Analysis:
        {style_hints}
        {price_hints}
        
        Rules:
        1. If brand needed - include it
        2. Maintain found style
        3. Consider colors and price segment
        
        Examples:
        - "gothic dark mens sneakers" (for opium style)
        - "acne studios mens hoodie"
        - "luxury mens pants black"
        
        Return only query (max 7 words):
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )
            
            query = response.choices[0].message.content.strip().replace('"', '')
            return query
            
        except Exception as e:
            logger.error(f"Query creation error: {e}")
            brand_part = f"{brands[0]} " if brands and brands[0] != "any" else ""
            return f"{brand_part}mens {category}"
    
    async def _select_best_item(self, results, category, brands, user_query, context, budget):
        if not results:
            return None
            
        if len(results) == 1:
            return results[0]
        
        # Prepare context for AI
        context_info = "First item in outfit"
        
        if context:
            items = []
            prices = []
            
            for item in context:
                details = item.get('details', {})
                price_str = item.get('price', '')
                title = item.get('title', '')
                
                price_match = re.search(r'[\d.,]+', str(price_str))
                if price_match:
                    try:
                        price = float(price_match.group().replace(',', ''))
                        prices.append(price)
                    except:
                        pass
                
                items.append(f"ITEM: {item.get('category')}")
                items.append(f"Title: {title[:60]}")
                items.append(f"Price: {price_str}")
                items.append(f"Color: {details.get('color')} | Style: {details.get('style')}")
                items.append("")
            
            context_info = f"Already in outfit:\n" + "\n".join(items)
        
        # Prepare options for selection
        options = []
        for i, result in enumerate(results[:8]):
            price_match = re.search(r'[\d.,]+', str(result.get('price', '')))
            price_num = 0
            if price_match:
                try:
                    price_num = float(price_match.group().replace(',', ''))
                except:
                    pass
            
            options.append({
                "index": i,
                "title": result.get("title", ""),
                "price": result.get("price", "N/A"),
                "price_num": price_num,
                "source": result.get("source", "Unknown")
            })
        
        brand_req = ""
        if brands and brands[0] != "any":
            brand_req = f"Required brand: {brands[0]}"
        
        budget_info = ""
        if budget and context:
            spent = sum(prices) if prices else 0
            left = budget - spent
            budget_info = f"Budget remaining: ${left:.0f}"
        
        prompt = f"""
        Select the best {category} for outfit.
        
        Query: "{user_query}"
        {brand_req}
        {budget_info}
        
        {context_info}
        
        Options:
        {json.dumps(options, ensure_ascii=False, indent=1)}
        
        All items already filtered (removed women's, fakes, wrong prices).
        
        Select best considering:
        1. Style unity
        2. Price harmony  
        3. Color compatibility
        4. Source quality
        
        If all poorly match - return "NONE".
        Otherwise return best index.
        
        Only index (0-7) or "NONE":
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            if "NONE" in content.upper():
                logger.warning(f"AI: no suitable items for {category}")
                return None
            
            match = re.search(r'\b([0-7])\b', content)
            if match:
                index = int(match.group(1))
                if 0 <= index < len(results):
                    item = results[index]
                    price = options[index]['price_num']
                    logger.info(f"AI selected #{index}: {item.get('title', '')[:50]}")
                    logger.info(f"Price: ${price:.0f} | Source: {item.get('source', 'Unknown')}")
                    return item
                    
        except Exception as e:
            logger.error(f"AI selection error: {e}")
        
        # Fallback logic
        if brands and brands[0] != "any":
            for result in results:
                if self._check_brand(result.get('title', ''), brands[0]):
                    if context and self._has_harmony_issues(result, context):
                        continue
                    logger.info(f"Fallback: found by brand")
                    return result
            
            logger.warning(f"Fallback: brand {brands[0]} not found")
            return None
        
        if context:
            for result in results:
                if not self._has_harmony_issues(result, context):
                    logger.info(f"Fallback: found harmonious item")
                    return result
            logger.warning(f"Fallback: all violate harmony")
            return None
        
        return results[0] if results else None
    
    def _filter_results(self, results, brands, context):
        filtered = []
        required_brand = brands[0] if brands and brands[0] != "any" else None
        
        # Analyze existing prices
        existing_prices = []
        if context:
            for item in context:
                price_str = item.get('price', '')
                price_match = re.search(r'[\d.,]+', str(price_str))
                if price_match:
                    try:
                        price = float(price_match.group().replace(',', ''))
                        if price > 0:
                            existing_prices.append(price)
                    except:
                        pass
        
        logger.info(f"Filtering {len(results)} results...")
        
        for i, result in enumerate(results):
            title = result.get('title', '').lower()
            price_str = result.get('price', '')
            source = result.get('source', '').lower()
            
            # Block women's items
            women_words = ['women\'s', 'womens', 'ladies', 'girl\'s', 'girls', 'female', 'wmns', 'women', 'lady']
            if any(word in title for word in women_words):
                logger.info(f"Filter: women's item #{i}")
                continue
            
            # Block kids items
            kids_words = ['kids', 'child', 'children', 'youth', 'junior', 'toddler']
            if any(word in title for word in kids_words):
                logger.info(f"Filter: kids item #{i}")
                continue
            
            # Block fakes
            fake_words = ['fake', 'knock-off', 'inspired by', 'style', 'alt', 'alternative', 'knock off']
            if any(word in title for word in fake_words):
                logger.info(f"Filter: fake #{i}")
                continue
            
            # Check brand (if needed)
            if required_brand and required_brand != "opium_style":
                if not self._check_brand_strict(result.get('title', ''), required_brand):
                    logger.info(f"Filter: wrong brand #{i}")
                    continue
            
            # Check price gap
            if existing_prices:
                price_match = re.search(r'[\d.,]+', str(price_str))
                if price_match:
                    try:
                        candidate_price = float(price_match.group().replace(',', ''))
                        
                        if candidate_price > 0:
                            max_existing = max(existing_prices)
                            min_existing = min(existing_prices)
                            max_ratio = max(candidate_price / min_existing, max_existing / candidate_price)
                            
                            if max_ratio > 10:
                                logger.info(f"Filter: price gap {max_ratio:.1f}x #{i}")
                                continue
                    except:
                        pass
            
            # Block items without price
            if price_str == 'N/A' or not price_str:
                logger.info(f"Filter: no price #{i}")
                continue
            
            # Block suspicious stores
            bad_sources = ['wish', 'aliexpress', 'alibaba', 'dhgate']
            if any(bad in source for bad in bad_sources):
                logger.info(f"Filter: bad store #{i}")
                continue
            
            # Item passed filters
            filtered.append(result)
            logger.info(f"Approved item #{i}")
        
        logger.info(f"Filtration: {len(filtered)} out of {len(results)} passed")
        return filtered
    
    def _has_harmony_issues(self, item, context):
        title = item.get('title', '').lower()
        price_str = item.get('price', '')
        
        # Women's items
        if any(word in title for word in ['women\'s', 'womens', 'ladies', 'girl\'s', 'female']):
            return True
        
        # Price gap
        if context:
            price_match = re.search(r'[\d.,]+', str(price_str))
            if price_match:
                try:
                    item_price = float(price_match.group().replace(',', ''))
                    
                    existing_prices = []
                    for ctx_item in context:
                        ctx_price_str = ctx_item.get('price', '')
                        ctx_match = re.search(r'[\d.,]+', str(ctx_price_str))
                        if ctx_match:
                            try:
                                ctx_price = float(ctx_match.group().replace(',', ''))
                                if ctx_price > 0:
                                    existing_prices.append(ctx_price)
                            except:
                                pass
                    
                    if existing_prices and item_price > 0:
                        max_ratio = max(item_price / min(existing_prices), max(existing_prices) / item_price)
                        if max_ratio > 8:
                            return True
                except:
                    pass
        
        # Fakes
        sus_words = ['alt', 'style', 'inspired', 'knock-off']
        if any(word in title for word in sus_words):
            return True
        
        return False
    
    def _check_brand_strict(self, title, brand):
        title_lower = title.lower()
        brand_lower = brand.lower()
        
        if brand_lower == "opium_style":
            return True  # Don't check specific brand for style
        elif brand_lower == "acne studios":
            return "acne studios" in title_lower
        elif brand_lower == "maison margiela":
            return any(term in title_lower for term in ['margiela', 'maison margiela', 'mm6'])
        else:
            return brand_lower in title_lower
    
    def _check_brand(self, title, brand):
        title_lower = title.lower()
        brand_lower = brand.lower()
        
        if brand_lower == "acne studios":
            return "acne studios" in title_lower
        elif brand_lower == "maison margiela":
            return "margiela" in title_lower or "maison margiela" in title_lower
        else:
            return brand_lower in title_lower
    
    async def _try_alternatives(self, category, brands, user_query, context, searcher):
        logger.info(f"Alternative strategies for {category}")
        
        brand = brands[0] if brands and brands[0] != "any" else None
        
        # Search by brand
        if brand:
            alt_queries = []
            
            if brand == "opium_style":
                alt_queries = [
                    "rick owens mens sneakers black",
                    "gothic dark mens sneakers",
                    "avant garde black mens sneakers", 
                    "dark aesthetic mens sneakers",
                    "balenciaga dark sneakers",
                    "all black luxury sneakers",
                    "edgy dark mens sneakers",
                    "minimalist dark sneakers"
                ]
            elif brand == "acne studios":
                alt_queries = [
                    "acne mens clothing",
                    "acne studios fashion",
                    f"scandinavian mens {category}",
                    f"acne brand {category}"
                ]
            elif brand == "maison margiela":
                alt_queries = [
                    f"margiela mens {category}",
                    f"maison margiela fashion",
                    f"margiela designer {category}",
                    f"mm6 mens {category}"
                ]
            else:
                alt_queries = [
                    f"{brand} mens {category}",
                    f"{brand.split()[0]} mens {category}",
                    f"designer {category} {brand}"
                ]
            
            for query in alt_queries:
                logger.info(f"Alternative search: '{query}'")
                try:
                    results = await searcher.search_serpapi(query, 8)
                    if results:
                        filtered = self._filter_results(results, brands, context)
                        if filtered:
                            best = await self._select_best_item(filtered, category, brands, user_query, context, None)
                            if best:
                                logger.info(f"Found via alternative: {best.get('title', '')[:50]}")
                                return best
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Alternative search error: {e}")
                    continue
        
        # Search by style
        if context:
            style_info = self._analyze_style(context)
            style_queries = [
                f"{style_info.get('style', 'casual')} mens {category}",
                f"mens {category} {style_info.get('color', 'neutral')}",
                f"{style_info.get('price_tier', 'premium')} mens {category}",
                f"mens {category} designer"
            ]
            
            for query in style_queries:
                logger.info(f"Style search: '{query}'")
                try:
                    results = await searcher.search_serpapi(query, 6)
                    if results:
                        filtered = self._filter_results(results, ["any"], context)
                        if filtered:
                            best = await self._select_best_item(filtered, category, ["any"], user_query, context, None)
                            if best:
                                logger.info(f"Found by style: {best.get('title', '')[:50]}")
                                return best
                    await asyncio.sleep(0.5)
                except Exception as e:
                    continue
        
        # Basic search
        basic_queries = [f"mens {category}", f"mens {category} fashion", f"men {category}"]
        
        for query in basic_queries:
            logger.info(f"Basic search: '{query}'")
            try:
                results = await searcher.search_serpapi(query, 5)
                if results:
                    filtered = self._filter_results(results, ["any"], context)
                    if filtered:
                        best = await self._select_best_item(filtered, category, ["any"], user_query, context, None)
                        if best:
                            logger.info(f"Found by basic search: {best.get('title', '')[:50]}")
                            return best
                await asyncio.sleep(0.5)
            except Exception as e:
                continue
        
        logger.warning(f"Failed to find {category}")
        return None
    
    def _analyze_style(self, context):
        styles = []
        colors = []
        prices = []
        
        for item in context:
            details = item.get('details', {})
            
            if details.get('style'):
                styles.append(details['style'])
            if details.get('color') != 'unknown':
                colors.append(details['color'])
            
            price_str = item.get('price', '')
            price_match = re.search(r'[\d.,]+', str(price_str))
            if price_match:
                try:
                    price = float(price_match.group().replace(',', ''))
                    prices.append(price)
                except:
                    pass
        
        main_style = max(set(styles), key=styles.count) if styles else 'casual'
        main_color = colors[0] if colors else "neutral"
        avg_price = sum(prices) / len(prices) if prices else 100
        
        price_tier = "luxury" if avg_price >= 300 else "premium" if avg_price >= 100 else "budget"
        
        return {
            'style': main_style,
            'color': main_color,
            'price_tier': price_tier
        }
    
    async def _check_harmony(self, items, user_query, budget):
        # Collect info about outfit
        analysis = []
        prices = []
        
        for item in items:
            details = item.get('details', {})
            price_str = item.get('price', '')
            
            price_match = re.search(r'[\d.,]+', str(price_str))
            price_val = 0
            if price_match:
                try:
                    price_val = float(price_match.group().replace(',', ''))
                    prices.append(price_val)
                except:
                    pass
            
            analysis.append(f"{item.get('category_ru')}: {item.get('title', '')[:50]}")
            analysis.append(f"Price: ${price_val:.0f} | Style: {details.get('style')} | Color: {details.get('color')}")
        
        total = sum(prices) if prices else 0
        
        prompt = f"""
        Rate this men's outfit as a stylist:
        
        Query: "{user_query}"
        Budget: ${budget} (spent: ${total:.0f})
        
        Outfit:
        {chr(10).join(analysis)}
        
        Are there serious problems with:
        1. Price harmony (gap >10x)
        2. Style unity
        3. Formality level
        4. Gender matching
        5. Color compatibility
        
        JSON:
        {{
            "is_good": true/false,
            "score": 1-10,
            "reason": "brief explanation",
            "issues": ["problems if any"]
        }}
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group(0))
                logger.info(f"Harmony check: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Harmony check error: {e}")
        
        # Simple check
        if len(prices) >= 2:
            max_ratio = max(prices) / min(prices) if min(prices) > 0 else 1
            if max_ratio > 10:
                return {
                    "is_good": False,
                    "score": 3,
                    "reason": f"Large price gap: {max_ratio:.1f}x",
                    "issues": ["Price disharmony"]
                }
        
        return {"is_good": True, "score": 7, "reason": "Basic check OK", "issues": []}
    
    async def _analyze_item(self, item):
        title = item.get('title', '')
        price = item.get('price', '')
        source = item.get('source', '')
        
        prompt = f"""
        Analyze item:
        
        ITEM: "{title}"
        PRICE: {price}
        STORE: {source}
        
        JSON:
        {{
            "color": "main color",
            "secondary_colors": ["additional colors"],
            "style": "style", 
            "formality": "formality level",
            "season": "season",
            "material_type": "material",
            "fit": "fit",
            "brand_tier": "brand level",
            "versatility": "versatility 1-10",
            "style_keywords": ["keywords"]
        }}
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.2
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                details = json.loads(json_match.group(0))
                logger.info(f"Analysis: color={details.get('color')} | style={details.get('style')}")
                return details
                
        except Exception as e:
            logger.error(f"Analysis error: {e}")
        
        return self._simple_analysis(title, price, source)
    
    def _simple_analysis(self, title, price, source):
        title_lower = title.lower()
        
        # Determine color
        color = "unknown"
        if 'black' in title_lower: color = 'black'
        elif 'white' in title_lower: color = 'white'
        elif 'navy' in title_lower: color = 'navy'
        elif 'blue' in title_lower: color = 'blue'
        elif 'gray' in title_lower or 'grey' in title_lower: color = 'gray'
        elif 'beige' in title_lower: color = 'beige'
        elif 'brown' in title_lower: color = 'brown'
        
        # Determine style
        style = "casual"
        if any(word in title_lower for word in ['sport', 'athletic', 'gym']):
            style = "sport"
        elif any(word in title_lower for word in ['formal', 'dress', 'business']):
            style = "formal"
        elif any(word in title_lower for word in ['street', 'urban', 'oversized']):
            style = "streetwear"
        
        # Price level
        price_num = 0
        if price and price != 'N/A':
            price_match = re.search(r'[\d.,]+', str(price))
            if price_match:
                try:
                    price_num = float(price_match.group().replace(',', ''))
                except:
                    pass
        
        brand_tier = "mid"
        if price_num >= 300: brand_tier = "luxury"
        elif price_num >= 100: brand_tier = "premium" 
        elif price_num >= 50: brand_tier = "mid"
        else: brand_tier = "budget"
        
        return {
            "color": color,
            "secondary_colors": [],
            "style": style,
            "formality": "casual",
            "season": "all_season",
            "material_type": "unknown",
            "fit": "regular",
            "brand_tier": brand_tier,
            "versatility": 5,
            "style_keywords": [style, color]
        }
    
    def _get_search_order(self, categories):
        # First search items with specific brands (usually more expensive)
        # Then match regular items to found price level
        
        branded_categories = []
        regular_categories = []
        
        # Separate into branded and regular
        for category in categories:
            if hasattr(self, 'brands_map') and self.brands_map.get(category, ["any"])[0] != "any":
                branded_categories.append(category)
            else:
                regular_categories.append(category)
        
        # Branded first, then regular
        result_order = branded_categories + regular_categories
        
        # If no brand info, use old logic
        if not branded_categories:
            priority = {
                'hoodie': 1, 'tshirt': 1, 'sweater': 1, 'jacket': 1,
                'pants': 2, 'shorts': 2, 'jeans': 2,
                'sneakers': 3, 'shoes': 3, 'accessories': 4
            }
            result_order = sorted(categories, key=lambda x: priority.get(x, 5))
        
        logger.info(f"Search order: {result_order}")
        logger.info(f"Branded first: {branded_categories}")
        return result_order

class FashionSearcher:
    def __init__(self, serpapi_key, ai_client):
        self.serpapi_key = serpapi_key
        self.ai_client = ai_client
    
    async def search(self, user_query):
        plan = await self._create_plan(user_query)
        
        if plan.get("is_outfit", False):
            return await self._search_outfit(user_query, plan)
        else:
            return await self._search_items(user_query, plan)
    
    async def _create_plan(self, user_query):
        prompt = f"""
        Analyze query: "{user_query}"
        
        Special cases:
        - "opium sneakers" → sneakers in dark gothic style
        - "acne studios hoodie" → hoodie from acne studios
        - "balenciaga tshirt" → tshirt from balenciaga
        - "under 1000" → budget_limit
        
        Categories:
        - hoodie/sweatshirt → "hoodie"
        - tshirt/t-shirt → "tshirt"
        - pants/trousers → "pants"  
        - shorts → "shorts"
        - sneakers/shoes → "sneakers"
        - jacket/coat → "jacket"
        
        Rules:
        1. If "look/outfit/complete" → is_outfit = true
        2. Find all clothing categories
        3. Match brands with categories
        4. Extract budget
        
        JSON:
        {{
            "is_outfit": true/false,
            "categories": ["list"],
            "brands_for_categories": {{"category": ["brand"]}},
            "budget_limit": number_or_null,
            "target_count": quantity
        }}
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group(0))
                logger.info(f"Search plan: {plan}")
                return plan
                
        except Exception as e:
            logger.error(f"Plan creation error: {e}")
        
        return self._fallback_plan(user_query)
    
    def _fallback_plan(self, user_query):
        query_lower = user_query.lower()
        
        is_outfit = any(word in query_lower for word in ["look", "outfit", "complete"])
        
        budget_match = re.search(r'under (\d+)', query_lower)
        budget = int(budget_match.group(1)) if budget_match else None
        
        if is_outfit:
            categories = []
            brands = {}
            
            if any(word in query_lower for word in ["hoodie", "sweatshirt"]):
                categories.append("hoodie")
                brands["hoodie"] = ["any"]
            
            if any(word in query_lower for word in ["tshirt", "t-shirt"]):
                categories.append("tshirt")
                brands["tshirt"] = ["any"]
                
            if any(word in query_lower for word in ["pants", "trousers"]):
                categories.append("pants")
                brands["pants"] = ["any"]
            
            if any(word in query_lower for word in ["sneakers", "shoes"]):
                categories.append("sneakers")
                brands["sneakers"] = ["any"]
            
            # Search for brands
            if "acne studios" in query_lower:
                if "hoodie" in categories:
                    brands["hoodie"] = ["acne studios"]
                elif "tshirt" in categories:
                    brands["tshirt"] = ["acne studios"]
            
            if "opium" in query_lower and "sneakers" in categories:
                brands["sneakers"] = ["opium_style"]
            
            if "balenciaga" in query_lower:
                if "sneakers" in categories:
                    brands["sneakers"] = ["balenciaga"]
                elif "tshirt" in categories:
                    brands["tshirt"] = ["balenciaga"]
            
            if not categories:
                categories = ["hoodie", "pants", "sneakers"]
                brands = {"hoodie": ["any"], "pants": ["any"], "sneakers": ["any"]}
            
            return {
                "is_outfit": True,
                "categories": categories,
                "brands_for_categories": brands,
                "budget_limit": budget,
                "target_count": len(categories)
            }
        else:
            return {
                "is_outfit": False,
                "categories": ["clothing"],
                "brands_for_categories": {},
                "budget_limit": budget,
                "target_count": 3
            }
    
    async def _search_outfit(self, user_query, plan):
        categories = plan.get("categories", [])
        brands_map = plan.get("brands_for_categories", {})
        
        logger.info(f"Outfit search: {categories}")
        logger.info(f"Brands: {brands_map}")
        
        results = []
        
        for category in categories:
            logger.info(f"Searching for {category}")
            
            brands = brands_map.get(category, ["any"])
            query = await self._create_query(category, brands, user_query)
            
            try:
                search_results = await self.search_serpapi(query, 6)
                logger.info(f"Found {len(search_results)} for {category}")
                
                if search_results:
                    best = await self._select_best(search_results, category, brands, user_query)
                    if best:
                        best['category'] = category
                        best['category_ru'] = self.get_display_name(category)
                        results.append(best)
                        logger.info(f"Selected: {best.get('title', '')[:50]}")
                
                await asyncio.sleep(0.8)
                
            except Exception as e:
                logger.error(f"Search error for {category}: {e}")
                continue
        
        return results
    
    async def _create_query(self, category, brands, user_query):
        category_map = {
            "hoodie": "mens hoodie", "tshirt": "mens t-shirt", "pants": "mens pants",
            "shorts": "mens shorts", "sneakers": "mens sneakers", "jacket": "mens jacket"
        }
        
        base_category = category_map.get(category, f"mens {category}")
        
        if brands and brands[0] != "any":
            brand = brands[0]
            
            if brand == "opium_style":
                return f"gothic dark avant garde mens sneakers"
            elif brand == "acne studios":
                return f"acne studios {base_category}"
            elif brand == "maison margiela":
                return f"margiela {base_category}"
            else:
                return f"{brand} {base_category}"
        else:
            return base_category
    
    async def _select_best(self, results, category, brands, user_query):
        if not results or len(results) == 1:
            return results[0] if results else None
        
        items = []
        for i, result in enumerate(results[:5]):
            items.append({
                "index": i,
                "title": result.get("title", "")[:80],
                "price": result.get("price", "N/A"),
                "source": result.get("source", "")
            })
        
        brands_needed = brands if brands and brands[0] != "any" else []
        
        prompt = f"""
        Select best {category} for "{user_query}"
        Required brands: {brands_needed}
        
        Options:
        {json.dumps(items, ensure_ascii=False, indent=1)}
        
        Criteria:
        1. Brand match
        2. Men's clothing
        3. Store quality
        4. Reasonable price
        
        Only index:
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            match = re.search(r'\d+', content)
            if match:
                index = int(match.group())
                if 0 <= index < len(results):
                    return results[index]
        except Exception as e:
            logger.error(f"Selection error: {e}")
        
        return results[0]
    
    def get_display_name(self, category):
        names = {
            "hoodie": "Hoodie", "tshirt": "T-Shirt", "pants": "Pants",
            "shorts": "Shorts", "sneakers": "Sneakers", "jacket": "Jacket"
        }
        return names.get(category, category.title())
    
    async def _search_items(self, user_query, plan):
        queries = await self._generate_queries(user_query)
        
        all_results = []
        for query in queries[:2]:
            try:
                results = await self.search_serpapi(query, 4)
                all_results.extend(results)
                await asyncio.sleep(0.5)
            except:
                continue
        
        return all_results[:plan.get("target_count", 3)]
    
    async def _generate_queries(self, user_query):
        prompt = f"""
        Create 2 queries for: "{user_query}"
        JSON: ["query1", "query2"]
        """
        
        try:
            response = await self.ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.5
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\[.*\]', content)
            if json_match:
                return json.loads(json_match.group(0))
        except:
            pass
        
        return [f"mens {user_query}", f"fashion {user_query}"]
    
    async def search_serpapi(self, query, max_results=5, retry=0):
        results = []
        
        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": self.serpapi_key,
            "num": max_results,
            "gl": "us",
            "hl": "en"
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(15)) as session:
                async with session.get("https://serpapi.com/search", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        shopping_results = data.get("shopping_results", [])
                        
                        for item in shopping_results:
                            if item.get("title"):
                                results.append({
                                    "title": item.get("title", ""),
                                    "price": item.get("price", "N/A"), 
                                    "link": item.get("link", ""),
                                    "image": item.get("thumbnail", ""),
                                    "source": item.get("source", "Unknown")
                                })
                        
                        logger.info(f"Found {len(results)} for '{query}'")
                        
                    elif response.status == 429 and retry < 2:
                        logger.warning(f"Rate limit for '{query}'")
                        await asyncio.sleep(2)
                        return await self.search_serpapi(query, max_results, retry + 1)
                    else:
                        logger.error(f"SerpAPI status {response.status}")
                        
                        if retry == 0 and len(query.split()) > 2:
                            simple_query = " ".join(query.split()[:2])
                            logger.info(f"Simplified query: '{simple_query}'")
                            return await self.search_serpapi(simple_query, max_results, retry + 1)
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout '{query}'")
            if retry < 1:
                await asyncio.sleep(1)
                return await self.search_serpapi(query, max_results, retry + 1)
        except Exception as e:
            logger.error(f"SerpAPI error: {e}")
            
            if retry == 0:
                alt_query = self._alt_query(query)
                if alt_query != query:
                    logger.info(f"Alternative: '{alt_query}'")
                    return await self.search_serpapi(alt_query, max_results, retry + 1)
        
        return results
    
    def _alt_query(self, original):
        query_lower = original.lower()
        
        alternatives = {
            'acne studios': 'acne',
            'maison margiela': 'margiela', 
            'stone island': 'stone',
            'rick owens': 'rick'
        }
        
        for brand, alt in alternatives.items():
            if brand in query_lower:
                return original.replace(brand, alt)
        
        words = original.split()
        return " ".join(words[:3]) if len(words) > 3 else original

class FashionBot:
    def __init__(self):
        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.ai_client = openai.AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=AI_BASE_URL)
        self.searcher = FashionSearcher(SERPAPI_KEY, self.ai_client)
        self.coordinator = OutfitCoordinator(self.ai_client)
        
        # Handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start(self, update: Update, context):
        user_name = update.effective_user.first_name or "friend"
        
        text = f"""
Fashion Bot with AI Coordination!

Capabilities:
• Understands what you need from your query
• Matches items in the same price segment  
• Knows specific brands and styles
• Considers your budget

Examples:
"outfit with acne studios hoodie and opium sneakers under $1000"
"find balenciaga look"
"streetwear outfit with tshirt"

AI decides what matches in style and price
        """
        await update.message.reply_text(text)
    
    async def help(self, update: Update, context):
        text = """
How coordination works:

ANALYSIS:
• Understands query and extracts details
• Determines needed clothing categories
• Matches brands with categories  
• Considers budget

SPECIAL PHRASES:
• "opium sneakers" → dark gothic sneakers
• "acne studios hoodie" → Acne Studios hoodies
• "under 1000" → budget control

SELECTION:
• Analyzes each item
• Compares with already found
• Chooses best combinations
• Maintains unified style and prices

Just describe what you want!
        """
        await update.message.reply_text(text)
    
    async def handle_message(self, update: Update, context):
        user_query = update.message.text
        user_name = update.effective_user.first_name or "friend"
        
        status = await update.message.reply_text("Analyzing query...")
        
        try:
            plan = await self.searcher._create_plan(user_query)
            
            if plan.get("is_outfit", False):
                await status.edit_text("Creating coordinated outfit...")
                results = await self.coordinator.search_outfit(user_query, plan, self.searcher)
            else:
                await status.edit_text("Searching for matching items...")
                results = await self.searcher._search_items(user_query, plan)
            
            if not results:
                await status.edit_text(f"Couldn't find items for '{user_query}'\n\nTry different brands")
                return
            
            await status.delete()
            await self._send_results(update, results, user_query, user_name, plan)
            
        except Exception as e:
            logger.error(f"Search error for '{user_query}': {e}")
            await status.edit_text("Search error, please try again")
    
    async def _send_results(self, update, results, query, user_name, plan):
        count = len(results)
        is_outfit = plan.get("is_outfit", False)
        budget = plan.get("budget_limit")
        expected = len(plan.get("categories", []))
        
        # Calculate total
        total = 0
        for item in results:
            price_str = item.get('price', '0')
            price_match = re.search(r'[\d.,]+', str(price_str))
            if price_match:
                try:
                    price = float(price_match.group().replace(',', ''))
                    total += price
                except:
                    pass
        
        # Header
        if is_outfit:
            if count < expected:
                header = f"{user_name}, created partial outfit {count} of {expected} items!\n\n"
                header += "Some brands unavailable\n"
            else:
                header = f"{user_name}, created complete outfit of {count} items!\n\n"
            
            header += f"Items matched in unified style and price segment\n"
            if total > 0:
                header += f"Total cost: ~${total:.0f}"
                if budget:
                    if total <= budget:
                        header += f" (within budget ${budget})"
                    else:
                        header += f" (over budget ${budget})"
                header += "\n"
            header += f"Query: '{query}'\n"
        else:
            header = f"{user_name}, found {count} options!\n\nFor: '{query}'\n"
        
        await update.message.reply_text(header)
        
        # Show items
        for i, item in enumerate(results, 1):
            emoji = self._get_emoji(item['title'])
            
            title = item['title']
            if len(title) > 70:
                title = title[:67] + "..."
            
            category_text = ""
            if is_outfit and item.get('category_ru'):
                category_text = f" • {item['category_ru']}"
            
            price = item.get('price', 'N/A')
            price_text = f"{price}" if price != 'N/A' else "Check price"
            
            coord_text = ""
            if is_outfit and i > 1:
                coord_text = f"\nMatched to other items"
            
            text = f"""
{emoji} #{i}{category_text} {title}

{price_text}
{item.get('source', 'Unknown')}{coord_text}
"""
            
            keyboard = None
            if item.get('link'):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("View", url=item['link'])]
                ])
            
            if item.get('image'):
                try:
                    await update.message.reply_photo(photo=item['image'], caption=text, reply_markup=keyboard)
                except:
                    await update.message.reply_text(text, reply_markup=keyboard)
            else:
                await update.message.reply_text(text, reply_markup=keyboard)
            
            await asyncio.sleep(0.3)
        
        # Final message
        if is_outfit:
            budget_msg = ""
            if budget and total > 0:
                if total <= budget:
                    budget_msg = f" and within budget ${budget}!"
                else:
                    left = budget - total
                    budget_msg = f" (${abs(left):.0f} over limit ${budget})"
            
            final = f"Outfit ready!"
            if count < expected:
                missing = []
                found_cats = [item.get('category') for item in results]
                for cat in plan.get("categories", []):
                    if cat not in found_cats:
                        missing.append(self.searcher.get_display_name(cat))
                
                if missing:
                    final += f"\n\nNot found: {', '.join(missing)}"
                    final += f"\nTry different brands?"
            else:
                final += f" All {count} items match perfectly{budget_msg}"
            
            final += f"\n\nNeed changes? Just ask!"
            
            await update.message.reply_text(final)
        else:
            await update.message.reply_text(f"All options matched! What did you like?")
    
    def _get_emoji(self, title):
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['shoe', 'sneaker', 'boot']):
            return "👟"
        elif any(word in title_lower for word in ['shirt', 'tee', 't-shirt']):
            return "👕"  
        elif any(word in title_lower for word in ['short']):
            return "🩳"
        elif any(word in title_lower for word in ['pants', 'jean', 'trouser']):
            return "👖"
        elif any(word in title_lower for word in ['hoodie', 'sweat']):
            return "🧥"
        else:
            return "👔"
    
    def run(self):
        print("Fashion Bot starting...")
        print("Press Ctrl+C to stop")
        
        try:
            self.app.run_polling(drop_pending_updates=True)
        except KeyboardInterrupt:
            print("\nBot stopped")
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            print("Fashion Bot terminated")

if __name__ == "__main__":
    bot = FashionBot()
    bot.run()
