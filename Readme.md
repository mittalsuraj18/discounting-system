# Readme

# Discounting system architecture

Below highlights how the architecture of the discounting system would look like.

# Discount config and examples

This is the config of an individual Discount entity.

```jsx
{
	id: uuid,
	name: human readable name,
	code: unique coupon code like NIKE20,
	filters:{
		include: [], # the filters to which the coupon gets applied to. (and filters)
		exclude: [], # the filters for which it should not get applied to (and filters)
		min_qty: number, # optional
		min_value: number # optional
	},
	eval:{
		category: item | total # which level to apply the discount,
		type: percent | flat | sku | item # on which parameter should the discount be given
		value: string # the value of the discount.
		max_value: number # optional: maximim discount applicable (always in value terms)
	},
	stackable: true | false,
	priority: number # lower gets applied first
}
```

Examples of discounts.

1. Puma buy 1 get 1 free
    
    ```jsx
    {
    	id: uuid,
    	name: puma buy 1 get 1,
    	code: PUMA_1_1,
    	filters:{
    		include: ["puma"],
    		exclude: [],
    		min_qty: 1,
    	},
    	eval:{
    		category: total
    		type: item
    		value: 1
    	},
    	stackable: true,
    	priority: 100
    }
    ```
    
2. icici credit card 10% of maximum 500 inr
    
    ```jsx
    {
    	id: uuid,
    	name: icici 10% off on 2000 inr max 500 rs,
    	code: ICICI_10,
    	filters:{
    		include: ["icici_credit_card"],
    		exclude: [],
    		min_value: 2000
    	},
    	eval:{
    		category: total
    		type: percent
    		value: 10,
    		max_value: 500
    	},
    	stackable: true,
    	priority: 900 # should always be applied last if multiple level offers are present.
    }
    ```
    

# Constraints.

1. How do you handle conflicting discounts?
    1. stackable: 
        1. if this is true, the discounts are stacked and final discounte value is computed.
        2. if this is false, the items are computed individually.
    
    Final computation is basically max(stacked_discounts, unstacked_1, unstacked_2) etc.
    
2. How do i decide how the discounts are applied.
    1. priority: Discounts are applied in the order of priority. if stackable is true.
3. How do you enforce upper thresholds on discount?
    1. Max value in eval group.

# Architecture diagram

1. Modular Monolith
    
    ```
    Modules
       ├── Cart
       │   ├── Add to cart ->  POST /cart/
       │   ├── Remove cart -> DELETE /card/:cartId
       │   └── Get cart -> GET /cart/:cartID
       ├── coupon
       │   ├── Validate a coupon -> GET /coupon/:code
       │   └── Create a new coupon (business teams) -> POST /coupon
       ├── Checkout
       │   └── checkout Module -> POST /checkout/:cartId
       └── Rule Engine
           └── Apply Discounts -> POST /rule/evaluate
    ```
    
    1. Can be split into microservice based on scale. Start with monolith with clear separation boundaries.
2. DataFlow diagram
    
    ```mermaid
    sequenceDiagram
                actor User
                actor Admin
                participant API
                participant Cart as Cart Module
                participant Coupon as Coupon Module
                participant Rule as Rule Engine
                participant Checkout as Checkout Module
                participant DB
    
                %% === ADD TO CART FLOW ===
                rect rgb(230, 245, 230)
                Note over User,DB: Add to Cart Flow
                User->>API: POST /cart/
                API->>Cart: createCart(items)
                Cart->>DB: INSERT cart.carts
                Cart-->>API: {cartId, items, totals}
                API-->>User: CartResponse
                end
    
                %% === COUPON VALIDATION FLOW ===
                rect rgb(252, 228, 236)
                Note over User,DB: Validate Coupon Flow
                User->>API: GET /coupon/:code
                API->>Coupon: validate(code, userId, cartId)
                Coupon->>DB: SELECT coupons.coupons
                Coupon->>Rule: checkRule(ruleId, context)
                Rule->>DB: SELECT rules.conditions
                Rule-->>Coupon: RuleCheckResult
                Coupon-->>API: ValidationResult
                API-->>User: {valid, discount, code}
                end
    
                %% === CHECKOUT FLOW (Orchestrates All) ===
                rect rgb(255, 248, 225)
                Note over User,DB: Checkout Flow - Calls Rule Engine for Discounts
                User->>API: POST /checkout/:cartId
                API->>Checkout: initCheckout(cartId)
    
                Checkout->>Cart: ICartService.getCart(cartId)
                Cart->>DB: SELECT cart.carts, items
                Cart-->>Checkout: Cart
    
                Checkout->>Rule: POST /rule/evaluate<br/>(cart, user, context)
                Rule->>DB: SELECT active rules, conditions
                Rule->>Rule: Calculate best discount combination
                Rule-->>Checkout: DiscountPlan{appliedRules[], total}
    
                Checkout->>Coupon: ICouponService.hold(couponIds)
                Coupon->>DB: UPDATE coupons.user_coupons
                Coupon-->>Checkout: Held
    
                Checkout->>DB: INSERT checkout.orders
                Checkout-->>API: CheckoutSession
                API-->>User: {sessionId, orderId, total}
                end
    
                %% === BUSINESS TEAM: CREATE COUPON ===
                rect rgb(243, 229, 245)
                Note over Admin,DB: Business Team - Create Coupon
                Admin->>API: POST /coupon
                API->>Coupon: createCoupon(config)
    
                alt New rule required
                    Coupon->>Rule: createRule(ruleData)
                    Rule->>DB: INSERT rules.rules, conditions
                    Rule-->>Coupon: ruleId
                end
    
                Coupon->>DB: INSERT coupons.coupons
                Coupon-->>API: CouponCreated
                API-->>Admin: {couponId, code, ruleId}
                end
    ```
   
# Reference for interview
1. **Refer the folder `src/modules/rules` for the overview of rule engine.**