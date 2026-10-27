import { Suspense } from "react";
import { PartWorkspace, WorkspaceSkeleton } from "@/components/part-workspace";

export default function PartPage({ params }: PageProps<"/parts/[partNumber]">) {
  // With Cache Components, request-specific params are read inside a Suspense boundary.
  return (
    <Suspense fallback={<WorkspaceSkeleton />}>
      {params.then(({ partNumber }) => (
        <PartWorkspace partNumber={decodeURIComponent(partNumber)} />
      ))}
    </Suspense>
  );
}
