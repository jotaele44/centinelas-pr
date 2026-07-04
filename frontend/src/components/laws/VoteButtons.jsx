import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Button } from "@/components/ui/button";
import { ThumbsUp, ThumbsDown, Loader2 } from "lucide-react";

export default function VoteButtons({ law, onVoteChange }) {
  const [userVote, setUserVote] = useState(null);
  const [loading, setLoading] = useState(false);
  const [votesPro, setVotesPro] = useState(law.votes_pro || 0);
  const [votesAgainst, setVotesAgainst] = useState(law.votes_against || 0);

  useEffect(() => {
    loadUserVote();
  }, [law.id]);

  const loadUserVote = async () => {
    try {
      const user = await appClient.auth.me();
      if (!user) return;
      const votes = await appClient.entities.Vote.filter({ law_id: law.id, created_by_id: user.id });
      if (votes.length > 0) setUserVote(votes[0]);
    } catch (err) {
      // ignore
    }
  };

  const handleVote = async (type) => {
    setLoading(true);
    try {
      const user = await appClient.auth.me();
      if (!user) {
        window.location.href = "/Login";
        return;
      }

      if (userVote) {
        if (userVote.vote_type === type) {
          // Toggle off
          await appClient.entities.Vote.delete(userVote.id);
          const update = type === "pro"
            ? { votes_pro: Math.max(0, votesPro - 1) }
            : { votes_against: Math.max(0, votesAgainst - 1) };
          await appClient.entities.Law.update(law.id, update);
          if (type === "pro") setVotesPro((v) => Math.max(0, v - 1));
          else setVotesAgainst((v) => Math.max(0, v - 1));
          setUserVote(null);
        } else {
          // Switch vote
          await appClient.entities.Vote.update(userVote.id, { vote_type: type });
          if (type === "pro") {
            await appClient.entities.Law.update(law.id, {
              votes_pro: votesPro + 1,
              votes_against: Math.max(0, votesAgainst - 1),
            });
            setVotesPro((v) => v + 1);
            setVotesAgainst((v) => Math.max(0, v - 1));
          } else {
            await appClient.entities.Law.update(law.id, {
              votes_against: votesAgainst + 1,
              votes_pro: Math.max(0, votesPro - 1),
            });
            setVotesAgainst((v) => v + 1);
            setVotesPro((v) => Math.max(0, v - 1));
          }
          setUserVote({ ...userVote, vote_type: type });
        }
      } else {
        // New vote
        await appClient.entities.Vote.create({
          law_id: law.id,
          vote_type: type,
          user_name: user.full_name || user.email || "Anónimo",
        });
        if (type === "pro") {
          await appClient.entities.Law.update(law.id, { votes_pro: votesPro + 1 });
          setVotesPro((v) => v + 1);
        } else {
          await appClient.entities.Law.update(law.id, { votes_against: votesAgainst + 1 });
          setVotesAgainst((v) => v + 1);
        }
        setUserVote({ vote_type: type });
      }

      if (onVoteChange) onVoteChange();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex gap-3">
      <Button
        variant={userVote?.vote_type === "pro" ? "default" : "outline"}
        onClick={() => handleVote("pro")}
        disabled={loading}
        className="flex-1 h-12"
      >
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ThumbsUp className="w-4 h-4 mr-2" />}
        A favor · {votesPro}
      </Button>
      <Button
        variant={userVote?.vote_type === "against" ? "destructive" : "outline"}
        onClick={() => handleVote("against")}
        disabled={loading}
        className="flex-1 h-12"
      >
        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ThumbsDown className="w-4 h-4 mr-2" />}
        En contra · {votesAgainst}
      </Button>
    </div>
  );
}