import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Bell, BellOff } from "lucide-react";

const CATEGORIES = [
  "educación", "salud", "transporte", "seguridad pública", "gobierno municipal",
  "energía", "asuntos del consumidor", "justicia", "nominaciones", "medio ambiente",
  "economía", "otro",
];

export default function CategorySubscription({ userEmail, userName }) {
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSubscriptions();
  }, []);

  const loadSubscriptions = async () => {
    try {
      const data = await appClient.entities.Subscription.filter({ user_email: userEmail });
      setSubscriptions(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const isSubscribed = (category) => subscriptions.some((s) => s.category === category);

  const toggleSubscription = async (category) => {
    const existing = subscriptions.find((s) => s.category === category);
    try {
      if (existing) {
        await appClient.entities.Subscription.delete(existing.id);
        setSubscriptions(subscriptions.filter((s) => s.id !== existing.id));
      } else {
        const newSub = await appClient.entities.Subscription.create({
          category,
          user_email: userEmail,
          user_name: userName,
        });
        setSubscriptions([...subscriptions, newSub]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="bg-card rounded-xl border border-border p-5">
      <h2 className="text-xl font-semibold mb-1 flex items-center gap-2">
        <Bell className="w-5 h-5" />
        Categorías que sigues
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        Recibe un correo electrónico cuando se publique una ley en las categorías que te interesan
      </p>
      {loading ? (
        <p className="text-sm text-muted-foreground">Cargando...</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => {
            const subscribed = isSubscribed(cat);
            return (
              <button
                key={cat}
                onClick={() => toggleSubscription(cat)}
                className={`text-sm px-3 py-1.5 rounded-full border transition-colors capitalize flex items-center gap-1.5 ${
                  subscribed
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background text-foreground border-border hover:border-primary/50"
                }`}
              >
                {subscribed ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />}
                {cat}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}