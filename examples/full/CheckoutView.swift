import SwiftUI

struct CheckoutView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Order summary")
            Text("Selected payment method")
            Button("Pay now") {
                // intent: submit_payment
            }
            .accessibilityIdentifier("checkout-pay-now")
        }
        .padding(24)
    }
}
