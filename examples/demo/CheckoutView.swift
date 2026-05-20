import SwiftUI

struct CheckoutView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Checkout")
            Button("Pay") {
                // intent: submit_payment
            }
        }
        .padding(24)
    }
}
